import asyncio
import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date
from importlib.metadata import version
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, BeforeValidator, Field

from hubd import reminders
from hubd.daemon import Hub, MergeConflict, NotFound, spec_text, step_json
from hubd.init import PROJECTS
from hubd.model import one_line
from hubd.notify import NotifySend
from hubd.runners.claude import ClaudeCodeRunner
from hubd.settings import load_settings
from hubd.states import InvalidTransition
from hubd.theme import FakeTheme, OmarchyTheme, ThemeSource
from hubd.theme import read as read_theme
from hubd.theme import watch as watch_theme
from hubd.vault import vault_path

HOST = "127.0.0.1"  # localhost only: the API has no auth
PORT = int(os.environ.get("HUBD_PORT", 8765))  # tests run a second hubd on another port
# shortcut: the built app is found next to the source, so it only runs from a source checkout.
WEB_DIST = Path(__file__).parents[2] / "web" / "dist"


class Changes(BaseModel):
    # Pasted lines are joined with spaces: the comment is one `comment:` field in the step file.
    comment: Annotated[str, BeforeValidator(one_line), Field(min_length=1)]


class RunEnded(BaseModel):
    session_id: str
    step: str


def create_app(
    hub: Hub | None = None,
    demo: bool = False,
    theme: ThemeSource | None = None,
    reminder_hour: int | None = None,
) -> FastAPI:
    """`reminder_hour` set: send deadline reminders (only `hubd serve`, never tests or demo)."""
    theme = theme or FakeTheme()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if hub is None:
            yield
            return
        stop = asyncio.Event()
        tasks = [asyncio.create_task(hub.watch(stop))]
        if isinstance(theme, OmarchyTheme):  # FakeTheme (demo, tests) never changes
            tasks.append(asyncio.create_task(watch_theme(theme, hub.emit, stop)))
        if reminder_hour is not None:
            path = reminders.state_path()
            tasks.append(asyncio.create_task(reminders.loop(hub, path, reminder_hour, stop)))
        yield
        stop.set()
        await asyncio.gather(*tasks)

    app = FastAPI(title="hubd", lifespan=lifespan)

    @app.exception_handler(InvalidTransition)
    async def conflict(_: Request, exc: InvalidTransition) -> JSONResponse:
        return JSONResponse({"detail": exc.reason}, status_code=409)

    @app.exception_handler(MergeConflict)
    async def merge_conflict(_: Request, exc: MergeConflict) -> JSONResponse:
        return JSONResponse({"detail": exc.reason, "files": exc.files}, status_code=409)

    @app.exception_handler(NotFound)
    async def not_found(_: Request, exc: NotFound) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=404)

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
        return [
            {"path": str(_relative(e.path, hub.vault)), "line": e.line, "message": e.message}
            for e in hub.index.errors
        ] + [{"path": str(theme.path), "line": None, "message": m} for m in read_theme(theme)[1]]

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
    async def start(project: str, step_id: str) -> dict:
        return (await hub.start(project, step_id)).model_dump(mode="json")

    @app.post("/steps/{project}/{step_id}/finish")
    async def finish(project: str, step_id: str) -> dict:
        return (await hub.finish(project, step_id)).model_dump(mode="json")

    @app.post("/steps/{project}/{step_id}/approve")
    async def approve(project: str, step_id: str) -> dict:
        step, commit = await hub.approve(project, step_id)
        return {**step.model_dump(mode="json"), "commit": commit}

    @app.post("/steps/{project}/{step_id}/changes")
    async def changes(project: str, step_id: str, body: Changes) -> dict:
        return (await hub.request_changes(project, step_id, body.comment)).model_dump(mode="json")

    @app.post("/steps/{project}/{step_id}/tasks/{n}/tick")
    async def tick(project: str, step_id: str, n: int) -> dict:
        return step_json(await hub.tick(project, step_id, n))

    @app.post("/runs/ended")
    async def run_ended(body: RunEnded) -> dict:
        return (await hub.run_ended(body.session_id, body.step)).model_dump(mode="json")

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
    """`hubd serve`: the real vault, Claude runner, notify-send and Omarchy theme."""
    vault = vault_path()
    settings = load_settings(vault / "hub.toml")
    url = f"http://{HOST}:{PORT}"
    hub = Hub(
        vault, lambda _: ClaudeCodeRunner(settings.terminal, url), NotifySend(), projects=PROJECTS
    )
    return create_app(hub, theme=OmarchyTheme(), reminder_hour=settings.reminder_hour)
