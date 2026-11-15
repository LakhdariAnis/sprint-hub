import asyncio
import json
import os
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import date
from importlib.metadata import version
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, BeforeValidator, Field, StringConstraints, ValidationError

from hubd import doctor, reminders, service
from hubd.chats import Chats, Full
from hubd.daemon import Hub, MergeConflict, NotFound, spec_text, step_json
from hubd.init import PROJECTS
from hubd.model import one_line
from hubd.notify import Click, NotifySend
from hubd.runners.base import Unavailable
from hubd.runners.chat import ChatEvent, ChatRunner, ClaudeChat
from hubd.runners.claude import ClaudeCodeRunner
from hubd.runners.fake import FakeChat
from hubd.settings import (
    Current,
    Settings,
    has_comments,
    load_current,
    reason,
    save_settings,
)
from hubd.states import InvalidTransition
from hubd.theme import FakeTheme, OmarchyTheme, ThemeSource
from hubd.theme import read as read_theme
from hubd.theme import watch as watch_theme
from hubd.transcript import Transcript, no_transcript, read_claude
from hubd.vault import vault_path

HOST = "127.0.0.1"  # localhost only: the API has no auth
PORT = int(os.environ.get("HUBD_PORT", 8765))  # tests run a second hubd on another port
# shortcut: the built app is found next to the source, so it only runs from a source checkout.
WEB_DIST = Path(__file__).parents[2] / "web" / "dist"


class Changes(BaseModel):
    # Pasted lines are joined with spaces: the comment is one `comment:` field in the step file.
    comment: Annotated[str, BeforeValidator(one_line), Field(min_length=1)]


class Approve(BaseModel):
    own_hours: float | None = Field(None, ge=0, allow_inf_nan=False)


class RunEnded(BaseModel):
    session_id: str
    step: str


class RunWaiting(RunEnded):
    kind: Literal["turn", "permission", "idle"]


class Presence(BaseModel):
    window: str
    focused: bool
    chat: str | None = None  # the chat the window shows, if any


class NewChat(BaseModel):
    project: str | None = None  # none: a plain chat in `chats/scratch/` of the vault
    sprint: int | None = None  # with a project: its context is told to Claude (606)
    step: str | None = None
    model: Literal["opus", "sonnet", "haiku"]
    effort: Literal["low", "medium", "high", "xhigh", "max"]  # `claude --effort`


class ChatChange(BaseModel):
    title: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
        | None
    ) = None
    open: bool | None = None  # false: out of the sidebar (`x`); the vault keeps the chat
    model: Literal["opus", "sonnet", "haiku"] | None = None
    effort: Literal["low", "medium", "high", "xhigh", "max"] | None = None


class ProjectChange(BaseModel):
    workspace: int | None = Field(ge=2, le=9)  # None: its runs open anywhere


class PermissionAnswer(BaseModel):
    answer: Literal["allow", "deny", "chat"]  # chat: Allow for this chat


class Message(BaseModel):
    text: Annotated[str, StringConstraints(pattern=r"\S")]  # not empty, not only spaces


def create_app(
    hub: Hub | None = None,
    demo: bool = False,
    theme: ThemeSource | None = None,
    reminder_hour: int | None = None,
    current: Current | None = None,
    chat: Callable[[ChatEvent], ChatRunner] = FakeChat,
    transcript: Transcript = no_transcript,
) -> FastAPI:
    """`reminder_hour` set: send deadline reminders (only `hubd serve`, never tests or demo).

    `chat` makes the chat runner: FakeChat unless `hubd serve` passes ClaudeChat. `transcript`
    reads a restarted chat's turns back: `hubd serve` passes `read_claude`.
    """
    theme = theme or FakeTheme()
    # hub.toml as hubd runs with it; `hour` is the live reminder hour, read by the reminder loop.
    current = current or (load_current(hub.vault / "hub.toml") if hub else Current(Settings()))
    hour = [reminder_hour]

    def popup(key: tuple[str, str], title: str, body: str, on_click: Click) -> bool:
        return current.settings.notify_waiting and hub.popup(key, title, body, on_click)

    chats = Chats(chat, hub.emit, hub.vault, hub.context, transcript, popup) if hub else None

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if hub is None:
            yield
            return
        chats.restore({p: hub.repo(p) for p in hub.index.projects})
        stop = asyncio.Event()
        tasks = [asyncio.create_task(hub.watch(stop)), asyncio.create_task(chats.loop(stop))]
        if isinstance(theme, OmarchyTheme):  # FakeTheme (demo, tests) never changes
            tasks.append(asyncio.create_task(watch_theme(theme, hub.emit, stop)))
        if reminder_hour is not None:
            path = reminders.state_path()
            tasks.append(asyncio.create_task(reminders.loop(hub, path, lambda: hour[0], stop)))
        yield
        stop.set()
        await asyncio.gather(*tasks)
        await chats.close_all()

    app = FastAPI(title="hubd", lifespan=lifespan)
    app.state.chats = chats  # tests reach the idle check through it

    @app.exception_handler(InvalidTransition)
    async def conflict(_: Request, exc: InvalidTransition) -> JSONResponse:
        return JSONResponse({"detail": exc.reason}, status_code=409)

    @app.exception_handler(MergeConflict)
    async def merge_conflict(_: Request, exc: MergeConflict) -> JSONResponse:
        return JSONResponse({"detail": exc.reason, "files": exc.files}, status_code=409)

    @app.exception_handler(Full)
    async def full(_: Request, exc: Full) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(NotFound)
    async def not_found(_: Request, exc: NotFound) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=404)

    @app.exception_handler(Unavailable)
    async def unavailable(_: Request, exc: Unavailable) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=503)

    @app.get("/health")
    def health() -> dict:
        body = {"ok": True, "version": version("hubd"), "demo": demo}
        if hub:  # the app says to run `hubd init` when there is no vault
            body |= {"vault": str(hub.vault), "vault_found": (hub.vault / "projects").is_dir()}
        return body

    @app.get("/theme")
    def get_theme() -> dict:
        return read_theme(theme)[0]  # read per request: the next reload picks up a theme switch

    if hub is None:
        return _with_web(app)

    @app.get("/projects")
    def projects() -> list[dict]:
        return [
            {"id": k, **p.model_dump(mode="json"), "repo_missing": hub.repo_missing(k)}
            for k, p in hub.index.projects.items()
        ]

    @app.post("/projects/{project}/focus")
    async def focus_project(project: str) -> dict:
        return {"workspace": await hub.focus(project)}

    @app.patch("/projects/{project}")
    async def change_project(project: str, body: ProjectChange) -> dict:
        await hub.set_workspace(project, body.workspace)
        return {"workspace": hub.index.projects[project].workspace}

    @app.get("/projects/{project}/steps")
    def project_steps(project: str) -> list[dict]:
        if project not in hub.index.projects:
            raise NotFound(f"no project {project}")
        return [step_json(e) for e in hub.index.steps if e.project == project]

    @app.get("/steps/{project}/{step_id}")
    def step(project: str, step_id: str) -> dict:
        entry = hub.entry(project, step_id)
        return {
            **step_json(entry),
            "spec": spec_text(entry),
            "path": str(entry.path),
            "command_model": hub.command_model(entry),
            "base": hub.index.projects[project].base,
        }

    @app.get("/steps/{project}/{step_id}/diffstat")
    async def diffstat(project: str, step_id: str) -> dict:
        return {"stat": await hub.diffstat(project, step_id)}

    @app.get("/today")
    def today() -> dict[str, list[dict]]:
        return {k: [step_json(e) for e in v] for k, v in hub.today().items()}

    @app.get("/week")
    def week() -> dict:
        return hub.week()

    @app.get("/projects/{project}/eta")
    def project_eta(project: str) -> dict:
        return hub.eta(project)

    @app.get("/questions")
    def questions() -> list[dict]:
        return [
            {"project": e.project, "step": e.step.step, "title": e.step.title, "text": q.text}
            for e in hub.index.steps
            for q in e.questions
            if not q.answered
        ]

    @app.get("/deadlines")
    def deadlines(days: int = Query(7, ge=0)) -> list[dict]:
        today = date.today()
        return [
            {**d.model_dump(mode="json"), "overdue": d.date < today}
            for d in hub.deadlines(days, today)
        ]

    @app.get("/errors")
    def errors() -> list[dict]:
        return (
            [
                {"path": str(_relative(e.path, hub.vault)), "line": e.line, "message": e.message}
                for e in hub.index.errors
            ]
            + [{"path": str(theme.path), "line": None, "message": m} for m in read_theme(theme)[1]]
            + [  # a sprint table with a bad row still works: a warning, not a broken file
                {"path": str(e.path), "line": e.line, "message": e.message, "level": "warning"}
                for e in hub.sprint_tables()[1]
            ]
        )

    @app.get("/doctor")
    def get_doctor() -> dict:
        return {
            "vault": str(hub.vault),
            "version": version("hubd"),
            "service": service.state(),
            "checks": doctor.report(hub.vault),
        }

    def settings_json() -> dict:
        path = hub.vault / "hub.toml"
        return {
            "path": str(path),
            **current.settings.model_dump(),
            "error": current.error,
            "comments": has_comments(path),
            "restart": [],  # all apply at once, see put_settings
        }

    @app.get("/settings")
    def get_settings() -> dict:
        return settings_json()

    @app.put("/settings", response_model=None)
    def put_settings(body: dict) -> JSONResponse | dict:
        try:
            new = Settings.model_validate(body)
        except ValidationError as exc:  # nothing written
            return JSONResponse({"detail": reason(exc)}, status_code=422)
        save_settings(hub.vault / "hub.toml", new)
        current.settings, current.error = new, None
        if hour[0] is not None:
            hour[0] = new.reminder_hour  # the reminder loop reads it on its next check
        if hasattr(hub.runner, "terminal"):
            hub.runner.terminal = new.terminal  # the next start opens it
        return settings_json()

    @app.get("/events")
    async def events() -> StreamingResponse:
        async def stream() -> AsyncIterator[str]:
            with hub.subscribe() as queue:
                yield ": connected\n\n"  # subscribed: events from now on reach this client
                while True:
                    event = await queue.get()
                    yield f"event: {event['type']}\ndata: {json.dumps(event)}\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.post("/steps/{project}/{step_id}/start")
    async def start(project: str, step_id: str, fresh: bool = False) -> dict:
        return (await hub.start(project, step_id, fresh)).model_dump(mode="json")

    @app.post("/steps/{project}/{step_id}/finish")
    async def finish(project: str, step_id: str) -> dict:
        return (await hub.finish(project, step_id)).model_dump(mode="json")

    @app.post("/steps/{project}/{step_id}/reopen")
    async def reopen(project: str, step_id: str) -> dict:
        return (await hub.reopen(project, step_id)).model_dump(mode="json")

    @app.post("/steps/{project}/{step_id}/approve")
    async def approve(project: str, step_id: str, body: Approve | None = None) -> dict:
        step, commit = await hub.approve(project, step_id, body.own_hours if body else None)
        return {**step.model_dump(mode="json"), "commit": commit}

    @app.post("/steps/{project}/{step_id}/changes")
    async def changes(project: str, step_id: str, body: Changes) -> dict:
        return (await hub.request_changes(project, step_id, body.comment)).model_dump(mode="json")

    @app.post("/steps/{project}/{step_id}/tasks/{n}/tick")
    async def tick(project: str, step_id: str, n: int) -> dict:
        return step_json(await hub.tick(project, step_id, n))

    if demo:

        @app.get("/demo/notifications")
        def demo_notifications() -> list[dict[str, str]]:
            return hub.notifier.sent  # type: ignore[attr-defined]  # RecordingNotifier

    @app.post("/presence")
    async def presence(body: Presence) -> dict:  # on the loop: no race on `windows`
        chats.present(body.window, body.focused, body.chat)
        return {"ok": True}

    @app.post("/chats", response_model=None)
    async def new_chat(body: NewChat) -> JSONResponse | dict:
        if body.project is None:
            cwd = hub.vault / "chats" / "scratch"
            cwd.mkdir(parents=True, exist_ok=True)
        elif body.project not in hub.index.projects:
            return JSONResponse({"detail": f"no project {body.project}"}, status_code=422)
        elif (cwd := hub.repo(body.project)) is None or not cwd.is_dir():
            return JSONResponse({"detail": f"project {body.project} has no repo"}, status_code=422)
        context = await hub.context(body.project, body.sprint, body.step) if body.project else None
        chat = await chats.open(
            body.project, cwd, body.model, body.effort, context, body.sprint, body.step
        )
        return {"id": chat.id, "context": context.json() if context else None}

    @app.get("/projects/{project}/context")
    async def chat_context(
        project: str, sprint: int | None = None, step: str | None = None
    ) -> dict:
        """What a new chat with these pills would be told: label, size, notes (the chip)."""
        return (await hub.context(project, sprint, step)).json()

    @app.get("/chats")
    def list_chats() -> list[dict]:
        return chats.listing()

    @app.get("/chats/{chat_id}")
    async def get_chat(chat_id: str) -> dict:
        return chats.json(await chats.load(chat_id))

    @app.patch("/chats/{chat_id}")
    async def change_chat(chat_id: str, body: ChatChange) -> dict:
        chat = await chats.edit(chat_id, body.title, body.open)
        if body.model or body.effort:
            chat = await chats.update(chat_id, body.model, body.effort)
        return chats.json(chat)

    @app.post("/chats/{chat_id}/message")
    async def message(chat_id: str, body: Message) -> dict:
        await chats.send(chat_id, body.text)
        return {"ok": True}

    @app.post("/chats/{chat_id}/permission/{request}")
    async def answer_permission(chat_id: str, request: str, body: PermissionAnswer) -> dict:
        chats.answer(chat_id, request, body.answer)
        return {"ok": True}

    @app.post("/chats/{chat_id}/stop")
    async def stop_chat(chat_id: str) -> dict:
        await chats.stop(chat_id)
        return {"ok": True}

    @app.post("/runs/ended")
    async def run_ended(body: RunEnded) -> dict:
        return (await hub.run_ended(body.session_id, body.step)).model_dump(mode="json")

    @app.post("/runs/waiting")
    async def run_waiting(body: RunWaiting) -> dict:  # on the loop: no race on `waited`
        notify = current.settings.notify_waiting  # Settings toggle, applies at once
        return {"sent": hub.run_waiting(body.session_id, body.step, body.kind, notify)}

    return _with_web(app)


def _with_web(app: FastAPI) -> FastAPI:
    """Serve the built Svelte app at `/`. Mounted last so the API routes match first."""
    if WEB_DIST.is_dir():
        app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")
    else:

        @app.get("/", response_class=PlainTextResponse)
        def no_web() -> str:
            return "The web app is not built. Run: cd web && npm install && npm run build\n"

    return app


def _relative(path: Path, root: Path) -> Path:
    return path.relative_to(root) if path.is_relative_to(root) else path


def serve_app() -> FastAPI:
    """`hubd serve`: the real vault, Claude runner and chat, notify-send and Omarchy theme."""
    vault = vault_path()
    current = load_current(
        vault / "hub.toml"
    )  # a broken file: defaults, the Settings screen says why
    url = f"http://{HOST}:{PORT}"
    hub = Hub(
        vault,
        lambda _: ClaudeCodeRunner(current.settings.terminal, url),
        NotifySend(),
        projects=PROJECTS,
    )
    return create_app(
        hub,
        theme=OmarchyTheme(),
        reminder_hour=current.settings.reminder_hour,
        current=current,
        chat=ClaudeChat,
        transcript=read_claude,
    )
