"""Step 656: the graph routes the chat and the Project page draw from."""

from pathlib import Path

from fastapi.testclient import TestClient
from test_approve import repo  # noqa: F401 (fixture)

from hubd.api import create_app
from hubd.daemon import Hub
from hubd.graph import FakeGraph, Graph, Node, find, report_facts
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


def test_affected_gives_ids_with_the_relation(vault: Path) -> None:
    c, _ = client(vault)
    body = c.get("/projects/demo/graph/affected", params={"node": "src_store_load"}).json()
    got = {a["id"]: a["relation"] for a in body["affected"]}
    assert got["src_api_list_items"] == "calls" and "src_ui_draw_list" in got
    one = c.get("/projects/demo/graph/affected?node=src_store_load&depth=1").json()
    assert {a["id"] for a in one["affected"]} == {"src_store", "src_api_list_items"}


def test_affected_unknown_node_is_404(vault: Path) -> None:
    c, _ = client(vault)
    assert c.get("/projects/demo/graph/affected?node=nope").status_code == 404
    assert c.get("/projects/demo/graph/affected?node=src_api&depth=0").status_code == 422


def test_path_in_order_or_empty(vault: Path) -> None:
    c, _ = client(vault)
    url = "/projects/demo/graph/path"
    assert c.get(url, params={"from": "src_ui_draw_list", "to": "src_store_load"}).json() == {
        "path": ["src_ui_draw_list", "src_api_list_items", "src_store_load"]
    }
    assert c.get(url, params={"from": "src_api", "to": "fastapi"}).json()["path"] == [
        "src_api",
        "fastapi",
    ]
    assert c.get(url, params={"from": "src_api", "to": "nope"}).status_code == 404


def test_path_off_and_failed(vault: Path) -> None:
    c, hub = client(vault, on=False)
    assert c.get("/projects/demo/graph/affected?node=x").status_code == 404
    save_graph(vault / "projects" / "demo" / "project.md", True)
    hub._reload_all()
    hub.graphs["demo"] = {"state": "failed", "reason": "boom"}
    assert c.get("/projects/demo/graph/path?from=a&to=b").status_code == 503


def test_report_god_nodes_groups_cycles_unread(vault: Path) -> None:
    c, _ = client(vault)
    body = c.get("/projects/demo/graph/report").json()
    assert body["god_nodes"][0]["id"] == "src_api_list_items"  # not a file, not fastapi
    assert len(body["god_nodes"]) == 6
    degrees = [n["degree"] for n in body["god_nodes"]]
    assert degrees == sorted(degrees, reverse=True)
    api = next(g for g in body["groups"] if g["name"] == "api")
    assert api["size"] == 4 and len(api["top"]) == 4
    assert body["cycles"] == [] and body["unread"] == {"count": 0, "top": []}


def test_report_facts_read_graphify_text() -> None:
    text = (
        "- Unclassified: 4 file(s) not represented in the graph (top: .ino 3, (none) 1)\n"
        "## Import Cycles\n- 3-file cycle: `a.py -> b.py -> c.py -> a.py`\n"
    )
    assert report_facts(text) == (
        [["a.py", "b.py", "c.py", "a.py"]],
        {"count": 4, "top": [".ino 3", "(none) 1"]},
    )
    assert report_facts("- Unclassified: 2 file(s) not represented in the graph")[1] == {
        "count": 2,
        "top": [],
    }
    assert report_facts("") == ([], {"count": 0, "top": []})


def test_find_matches_label_or_file(vault: Path) -> None:
    c, _ = client(vault)

    def ids(q: str) -> set[str]:
        body = c.get("/projects/demo/graph/find", params={"q": q}).json()
        return {n["id"] for n in body["nodes"]}

    assert ids("LOAD") == {"src_store_load"}
    assert ids("src/ui.py") == {"src_ui", "src_ui_draw_list", "src_ui_sort_items"}
    assert ids("") == set() and ids("zzz") == set()


def test_find_is_capped_at_20(vault: Path) -> None:
    nodes = [Node(f"n{i}", f"feats{i}()", "a.py", i, 0, "g", 0) for i in range(30)]
    assert len(find(Graph(nodes, [], {}, None, ""), "feats")) == 20
