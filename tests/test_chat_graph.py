"""Step 657: Claude uses the project's code graph in chats."""

import asyncio
import shutil
from pathlib import Path

import pytest

from hubd.daemon import Hub
from hubd.graph import GraphifyGraph
from hubd.notify import NullNotifier
from hubd.runners.fake import FakeRunner
from hubd.vault import save_graph

FIXTURES = Path(__file__).parent / "fixtures" / "graphify"


@pytest.fixture
def graphs(tmp_path: Path) -> Path:
    """A graphs root holding the fixture graph as the demo project's."""
    root = tmp_path / "graphs"
    (root / "demo").mkdir(parents=True)
    shutil.copy(FIXTURES / "graph.json", root / "demo" / "graph.json")
    return root


def make(vault: Path, graphs: Path) -> Hub:
    graph = GraphifyGraph(root=graphs, exe="no-graphify-here")
    return Hub(vault, lambda ended: FakeRunner(ended, delay=0), NullNotifier(), graph=graph)


def test_context_has_the_graph_block_only_when_on(vault: Path, graphs: Path) -> None:
    hub = make(vault, graphs)
    off = asyncio.run(hub.context("demo", None, None))
    assert "graph" not in off.parts and "graphify" not in off.text

    save_graph(vault / "projects" / "demo" / "project.md", True)
    hub = make(vault, graphs)
    on = asyncio.run(hub.context("demo", None, None))
    path = graphs / "demo" / "graph.json"
    assert on.parts[-1] == "graph" and "graph" in on.json()["label"]
    assert f"is at {path}: 38 nodes, 107 links, built from commit 0ea533d" in on.text
    for verb in ("query", "path", "affected", "explain"):
        assert f"`graphify {verb} " in on.text and f"--graph {path}`" in on.text
    assert "Prefer these for structure questions" in on.text
    assert on.text.index("## Code graph") < on.text.index("## Project")  # the cap cuts the end


def test_no_block_when_on_but_never_built(vault: Path, tmp_path: Path) -> None:
    save_graph(vault / "projects" / "demo" / "project.md", True)
    hub = make(vault, tmp_path / "empty")
    ctx = asyncio.run(hub.context("demo", None, None))
    assert "graph" not in ctx.parts and "graphify" not in ctx.text
