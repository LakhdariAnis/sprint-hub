import json
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import httpx2
import uvicorn
from conftest import Recorder
from fastapi import FastAPI

from hubd.api import create_app
from hubd.daemon import Hub
from hubd.runners.fake import FakeRunner


@contextmanager
def serve(app: FastAPI) -> Iterator[str]:
    """A real server in a thread: TestClient buffers streams, SSE needs a real socket."""
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning"))
    thread = threading.Thread(target=server.run)
    thread.start()
    try:
        while not server.started:
            time.sleep(0.01)
        port = server.servers[0].sockets[0].getsockname()[1]
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join()


def test_fake_run_shows_doing_ticks_done(vault: Path) -> None:
    hub = Hub(vault, lambda ended: FakeRunner(ended, delay=0.2), Recorder())
    events: list[dict] = []
    with serve(create_app(hub)) as url:
        with httpx2.stream("GET", f"{url}/events", timeout=5) as response:
            lines = response.iter_lines()
            assert next(lines) == ": connected"
            time.sleep(0.2)  # let the watcher start
            assert httpx2.post(f"{url}/steps/demo/104/start").status_code == 200
            for line in lines:
                if line.startswith("data: "):
                    events.append(json.loads(line.removeprefix("data: ")))
                    if events[-1]["type"] == "step" and events[-1]["state"] == "done":
                        break
    states = [e["state"] for e in events if e["type"] == "step"]
    assert states == ["doing", "done"]
    ticks = [[t["state"] for t in e["tasks"]] for e in events if e["type"] == "tasks"]
    assert ["doing", "todo"] in ticks
    assert ticks[-1] == ["done", "done"]
