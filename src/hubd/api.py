import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import version
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from hubd.daemon import Hub, MergeConflict, NotFound, step_json, vault_path
from hubd.notify import NotifySend
from hubd.runners.claude import ClaudeCodeRunner
from hubd.settings import load_settings
from hubd.states import InvalidTransition

HOST = "127.0.0.1"  # localhost only: the API has no auth
PORT = 8765
# shortcut: the built app is found next to the source, so it only runs from a source checkout.
WEB_DIST = Path(__file__).parents[2] / "web" / "dist"


class Changes(BaseModel):
    # One line: the comment is one `comment:` field in the step file.
    comment: str = Field(min_length=1, pattern=r"^[^\r\n]*\S[^\r\n]*$")


class RunEnded(BaseModel):
    session_id: str
    step: str


def create_app(hub: Hub | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if hub is None:
            yield
            return
        stop = asyncio.Event()
        watcher = asyncio.create_task(hub.watch(stop))
        yield
        stop.set()
        await watcher

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
        return {"ok": True, "version": version("hubd")}

    if hub is None:
        return _with_web(app)

    @app.get("/projects")
    def projects() -> list[dict]:
        return [{"id": k, **p.model_dump(mode="json")} for k, p in hub.index.projects.items()]

    @app.get("/projects/{project}/steps")
    def project_steps(project: str) -> list[dict]:
        if project not in hub.index.projects:
            raise NotFound(f"no project {project}")
        return [step_json(e) for e in hub.index.steps if e.project == project]

    @app.get("/steps/{project}/{step_id}")
    def step(project: str, step_id: str) -> dict:
        entry = hub.entry(project, step_id)
        spec = entry.spec.read_text() if entry.spec and entry.spec.is_file() else None
        return {**step_json(entry), "spec": spec, "path": str(entry.path)}

    @app.get("/steps/{project}/{step_id}/diffstat")
    async def diffstat(project: str, step_id: str) -> dict:
        return {"stat": await hub.diffstat(project, step_id)}

    @app.get("/today")
    def today() -> dict[str, list[dict]]:
        return {k: [step_json(e) for e in v] for k, v in hub.today().items()}

    @app.get("/errors")
    def errors() -> list[dict]:
        return [
            {"path": str(_relative(e.path, hub.vault)), "line": e.line, "message": e.message}
            for e in hub.index.errors
        ]

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

    @app.post("/steps/{project}/{step_id}/approve")
    async def approve(project: str, step_id: str) -> dict:
        return (await hub.approve(project, step_id)).model_dump(mode="json")

    @app.post("/steps/{project}/{step_id}/changes")
    async def changes(project: str, step_id: str, body: Changes) -> dict:
        return (await hub.request_changes(project, step_id, body.comment)).model_dump(mode="json")

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
    """`hubd serve`: the real vault, Claude runner and notify-send."""
    vault = vault_path()
    terminal = load_settings(vault / "hub.toml").terminal
    url = f"http://{HOST}:{PORT}"
    return create_app(Hub(vault, lambda _: ClaudeCodeRunner(terminal, url), NotifySend()))
