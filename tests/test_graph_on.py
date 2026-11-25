"""Step 655: `graph: on` per project, and the builds that keep it fresh."""

import asyncio
import threading
from pathlib import Path

from hubd.daemon import Hub
from hubd.graph import Built, FakeGraph
from hubd.notify import NullNotifier
from hubd.runners.fake import FakeRunner
from hubd.vault import _load_project, save_graph

PROJECT = "---\r\nname: p\r\nmodel: sonnet  # kept\r\nmerge: manual\r\n---\r\nbody\r\n"


def test_graph_line_comes_and_goes_byte_safe(tmp_path: Path) -> None:
    path = tmp_path / "project.md"
    path.write_bytes(PROJECT.encode())
    assert _load_project(path).graph is False
    save_graph(path, True)
    assert b"graph: on\r\n" in path.read_bytes()
    assert _load_project(path).graph is True
    save_graph(path, True)
    assert path.read_bytes().count(b"graph:") == 1
    save_graph(path, False)
    assert path.read_bytes() == PROJECT.encode()


class Counting(FakeGraph):
    """A FakeGraph that counts builds and holds each one until `go` is set."""

    def __init__(self, reason: str | None = None) -> None:
        super().__init__()
        self.calls: list[tuple[Path, str | None]] = []
        self.go = threading.Event()
        self.go.set()
        self.why = reason

    def build(self, project_path: str | Path, project: str | None = None) -> Built:
        self.calls.append((Path(project_path), project))
        self.go.wait(5)
        return Built(reason=self.why) if self.why else super().build(project_path, project)


def turn_on(vault: Path, project: str = "demo") -> None:
    save_graph(vault / "projects" / project / "project.md", True)


async def settle(hub: Hub) -> None:
    while hub.builds:
        await asyncio.sleep(0.01)


def make(vault: Path, graph: Counting) -> tuple[Hub, list[dict]]:
    hub = Hub(vault, lambda ended: FakeRunner(ended, delay=0), NullNotifier(), graph=graph)
    events: list[dict] = []
    hub.emit = events.append  # type: ignore[method-assign]
    return hub, events


def test_off_never_builds(vault: Path) -> None:
    graph = Counting()
    hub, events = make(vault, graph)

    async def main() -> None:
        hub.rebuild("demo")
        await settle(hub)

    asyncio.run(main())
    assert graph.calls == [] and events == [] and hub.graphs == {}


def test_on_builds_once_with_status_and_events(vault: Path) -> None:
    turn_on(vault)
    graph = Counting()
    hub, events = make(vault, graph)
    hub.graphs.clear()  # FakeGraph has a graph for every project already

    async def main() -> None:
        hub.rebuild("demo")
        await settle(hub)

    asyncio.run(main())
    assert graph.calls == [(vault / "demo-repo", "demo")]
    assert [e["type"] for e in events] == ["graph_building", "graph_built"]
    assert hub.graphs["demo"]["state"] == "built" and hub.graphs["demo"]["nodes"] == 10


def test_builds_do_not_pile_up(vault: Path) -> None:
    turn_on(vault)
    graph = Counting()
    graph.go.clear()
    hub, _ = make(vault, graph)

    async def main() -> None:
        for _ in range(5):  # one runs, the other four ask become one more
            hub.rebuild("demo")
            await asyncio.sleep(0.01)
        graph.go.set()
        await settle(hub)

    asyncio.run(main())
    assert len(graph.calls) == 2


def test_a_failed_build_says_why(vault: Path) -> None:
    turn_on(vault)
    hub, events = make(vault, Counting(reason="graphify not on PATH"))

    async def main() -> None:
        hub.rebuild("demo")
        await settle(hub)

    asyncio.run(main())
    assert hub.graphs["demo"] == {"state": "failed", "reason": "graphify not on PATH"}
    assert events[-1] == {"type": "graph_failed", "project": "demo", **hub.graphs["demo"]}


def test_status_of_a_graph_built_before_hubd_started(vault: Path) -> None:
    turn_on(vault)
    hub, _ = make(vault, Counting())
    assert hub.graphs == {
        "demo": {"state": "built", "nodes": 10, "at": "2026-11-25T09:00:00+00:00"}
    }
