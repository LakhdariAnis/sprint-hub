"""Step 660: `POST /projects/{name}/explainer` writes `explainer.md` through a ChatRunner."""

import asyncio
from pathlib import Path

import frontmatter
from fastapi.testclient import TestClient
from test_api_chats import until

from hubd.api import create_app
from hubd.daemon import Hub
from hubd.explainer import Explainers, _Job
from hubd.runners.fake import GRAPH_COMMAND, FakeChat
from hubd.vault import save_graph


def client(hub: Hub, delay: float = 0, graph: bool = True) -> tuple[TestClient, list[dict]]:
    """A client on the demo project (graph on) and the `explainer_*` events hubd emitted."""
    if graph:
        save_graph(hub.vault / "projects" / "demo" / "project.md", True)
        hub._reload_all()
    events: list[dict] = []
    emit = hub.emit
    hub.emit = lambda e: (events.append(e) if e["type"].startswith("explainer") else None, emit(e))
    return TestClient(create_app(hub, chat=lambda on: FakeChat(on, delay=delay))), events


def test_it_lands_next_to_project_md_with_progress_and_done(vault: Path, hub: Hub) -> None:
    c, events = client(hub)
    with c:
        assert c.post("/projects/demo/explainer").status_code == 202
        until(lambda: events and events[-1]["type"] in ("explainer_done", "explainer_failed"))
    path = vault / "projects" / "demo" / "explainer.md"
    assert [e["type"] for e in events] == [
        "explainer_started",
        "explainer_progress",
        "explainer_done",
    ]
    assert events[-1]["path"] == str(path) and events[-1]["cost_usd"] == 0.02
    meta = frontmatter.load(path).metadata
    assert meta["model"] == hub.index.projects["demo"].model and meta["cost"] == 0.02
    assert set(meta) >= {"written", "commit", "model", "type", "cost"}


def test_a_second_post_while_one_runs_is_409(hub: Hub) -> None:
    c, events = client(hub, delay=0.2)
    with c:
        assert c.post("/projects/demo/explainer").status_code == 202
        second = c.post("/projects/demo/explainer")
        assert second.status_code == 409 and "being written" in second.json()["detail"]
        until(lambda: events[-1]["type"] == "explainer_done")
        assert c.post("/projects/demo/explainer").status_code == 202  # done: it may run again


def test_no_graph_or_no_project_is_404(hub: Hub) -> None:
    c, _ = client(hub, graph=False)
    with c:
        assert "has no graph" in c.post("/projects/demo/explainer").json()["detail"]
        assert c.post("/projects/nope/explainer").status_code == 404


def test_it_only_reads_the_graph() -> None:
    graph = Path("/g/graph.json")
    ex = Explainers(lambda on: FakeChat(on), lambda e: None)
    ex.jobs["c1"] = _Job("demo", graph)
    command = GRAPH_COMMAND.replace("graph.json", str(graph))

    def ask(tool: str, given: dict) -> str:
        return asyncio.run(ex.ask("c1", tool, given))["behavior"]

    assert ask("Bash", {"command": command}) == "allow"
    assert ask("Bash", {"command": "rm -rf /"}) == "deny"
    assert ask("Write", {"file_path": "/r/a.py"}) == "deny"
    assert asyncio.run(ex.ask("other", "Bash", {"command": command}))["behavior"] == "deny"


def test_an_error_fails_it_and_writes_nothing(vault: Path, hub: Hub) -> None:
    c, events = client(hub)
    with c:
        app_explainers = c.app.state.explainers
        original = app_explainers.runner.send

        async def broken(chat_id: str, text: str) -> None:
            await app_explainers.on_event(chat_id, {"type": "error", "message": "claude died"})

        app_explainers.runner.send = broken
        c.post("/projects/demo/explainer")
        until(lambda: events[-1]["type"] == "explainer_failed")
        app_explainers.runner.send = original
    assert events[-1]["reason"] == "claude died"
    assert not (vault / "projects" / "demo" / "explainer.md").exists()
