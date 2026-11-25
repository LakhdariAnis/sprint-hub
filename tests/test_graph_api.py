"""Step 656: the graph routes the chat and the Project page draw from."""

from pathlib import Path

from fastapi.testclient import TestClient
from test_approve import repo  # noqa: F401 (fixture)

from hubd.api import create_app
from hubd.daemon import Hub
from hubd.graph import FakeGraph
from hubd.notify import NullNotifier
from hubd.runners.fake import FakeRunner
from hubd.vault import save_graph


def client(vault: Path, on: bool = True) -> tuple[TestClient, Hub]:
    if on:
        save_graph(vault / "projects" / "demo" / "project.md", True)
    hub = Hub(vault, lambda ended: FakeRunner(ended, delay=0), NullNotifier(), graph=FakeGraph())
    return TestClient(create_app(hub)), hub


def test_graph_has_nodes_links_groups(vault: Path) -> None:
    c, _ = client(vault)
    body = c.get("/projects/demo/graph").json()
    assert len(body["nodes"]) == 10 and len(body["links"]) == 13
    assert body["groups"][0] == {"id": 0, "name": "api"}
    assert body["built_at"] == "2026-11-25T09:00:00+00:00"
    assert body["stale"] is False
    assert {"id", "label", "file", "line", "group", "degree"} <= body["nodes"][0].keys()


def test_graph_off_is_404_with_a_reason(vault: Path) -> None:
    r = client(vault, on=False)[0].get("/projects/demo/graph")
    assert r.status_code == 404 and "turn it on" in r.json()["detail"]


def test_no_such_project_is_404(vault: Path) -> None:
    assert client(vault)[0].get("/projects/nope/graph").status_code == 404


def test_failed_build_is_503_with_the_reason(vault: Path) -> None:
    c, hub = client(vault)
    hub.graphs["demo"] = {"state": "failed", "reason": "graphify not on PATH"}
    r = c.get("/projects/demo/graph")
    assert r.status_code == 503 and "graphify not on PATH" in r.json()["detail"]


def test_no_graph_file_is_503(vault: Path) -> None:
    c, hub = client(vault)
    hub.graph.load = lambda project: None  # type: ignore[method-assign]
    assert c.get("/projects/demo/graph").status_code == 503


def test_stale_when_commit_is_not_head(vault: Path, repo: Path) -> None:  # noqa: F811
    c, hub = client(vault)
    hub.graph.graph = hub.graph.graph.__class__(
        hub.graph.graph.nodes, hub.graph.graph.links, hub.graph.graph.groups,
        "0" * 40, "2026-11-25T09:00:00+00:00",
    )  # fmt: skip
    assert c.get("/projects/demo/graph").json()["stale"] is True
