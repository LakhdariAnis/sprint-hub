from importlib.metadata import version

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from hubd.daemon import Hub, NotFound, vault_path
from hubd.notify import NotifySend
from hubd.runners.claude import ClaudeCodeRunner
from hubd.settings import load_settings
from hubd.states import InvalidTransition

HOST = "127.0.0.1"  # localhost only: the API has no auth
PORT = 8765


class RunEnded(BaseModel):
    session_id: str
    step: str


def create_app(hub: Hub | None = None) -> FastAPI:
    app = FastAPI(title="hubd")

    @app.exception_handler(InvalidTransition)
    async def conflict(_: Request, exc: InvalidTransition) -> JSONResponse:
        return JSONResponse({"detail": exc.reason}, status_code=409)

    @app.exception_handler(NotFound)
    async def not_found(_: Request, exc: NotFound) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=404)

    @app.get("/health")
    def health() -> dict:
        return {"ok": True, "version": version("hubd")}

    if hub is None:
        return app

    @app.post("/steps/{project}/{step_id}/start")
    async def start(project: str, step_id: str) -> dict:
        return (await hub.start(project, step_id)).model_dump(mode="json")

    @app.post("/runs/ended")
    async def run_ended(body: RunEnded) -> dict:
        return (await hub.run_ended(body.session_id, body.step)).model_dump(mode="json")

    return app


def serve_app() -> FastAPI:
    """`hubd serve`: the real vault, Claude runner and notify-send."""
    vault = vault_path()
    terminal = load_settings(vault / "hub.toml").terminal
    url = f"http://{HOST}:{PORT}"
    return create_app(Hub(vault, lambda _: ClaudeCodeRunner(terminal, url), NotifySend()))
