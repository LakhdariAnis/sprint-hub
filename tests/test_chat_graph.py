"""Step 657: Claude uses the project's code graph in chats."""

import asyncio
import shutil
from pathlib import Path

import pytest

from hubd import permits
from hubd.chats import Chats
from hubd.daemon import Hub
from hubd.graph import GraphifyGraph, ids_in, read
from hubd.notify import NullNotifier
from hubd.runners.chat import tool_line
from hubd.runners.fake import FakeChat, FakeRunner
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


GRAPH = Path("/home/a/.local/share/sprint-hub/graphs/tinyml/graph.json")


@pytest.mark.parametrize(
    "command",
    [
        f'graphify query "what calls chronological_split" --graph {GRAPH}',
        f'graphify path "load1_split()" "chronological_split()" --graph {GRAPH} --undirected',
        f"graphify affected 'chronological_split()' --depth 3 --graph {GRAPH}",
        f'graphify explain "split.py" --graph {GRAPH}',
        f'graphify query "a; b && c | d" --graph "{GRAPH}"',  # quoted: one argument, no shell
    ],
)
def test_the_four_read_commands_need_no_card(command: str) -> None:
    assert permits.graph_read("Bash", {"command": command}, GRAPH)


@pytest.mark.parametrize(
    "command",
    [
        "ls",
        f"graphify add https://example.com --graph {GRAPH}",
        f"graphify update . --graph {GRAPH}",
        f'graphify query "x" --graph {GRAPH}; rm -rf ~',
        f'graphify query "x" --graph {GRAPH} && ls',
        f'graphify query "x" --graph {GRAPH} | tee out',
        f'graphify query "x" --graph {GRAPH} > out',
        f'graphify query "$(rm -rf ~)" --graph {GRAPH}',
        f'graphify query "`ls`" --graph {GRAPH}',
        f'graphify query "x" --graph {GRAPH}\nls',
        f"graphify explain main() --graph {GRAPH}",  # unquoted (): a shell syntax error
        'graphify query "x"',  # no --graph: graphify-out/ of the folder
        'graphify query "x" --graph /tmp/other.json',
        f'graphify query "x" --graph {GRAPH} --graph /tmp/other.json',
        f'graphify query "x" --graph={GRAPH}',
        f'GRAPHIFY_OUT=/tmp graphify query "x" --graph {GRAPH}',
        f'/usr/bin/graphify query "x" --graph {GRAPH}',
        f'graphify query "x --graph {GRAPH}',  # open quote
        f'graphify query "x" --graph {GRAPH} &',
    ],
)
def test_anything_else_still_asks(command: str) -> None:
    assert not permits.graph_read("Bash", {"command": command}, GRAPH)


def test_not_bash_or_no_graph_asks() -> None:
    command = {"command": f'graphify query "x" --graph {GRAPH}'}
    assert not permits.graph_read("PowerShell", command, GRAPH)
    assert not permits.graph_read("Bash", command, None)
    assert not permits.graph_read("Bash", {"command": 3}, GRAPH)


def test_chats_allow_graph_reads_without_a_card(tmp_path: Path) -> None:
    events: list[dict] = []
    chats = Chats(
        lambda on_event: FakeChat(on_event, delay=0), events.append, tmp_path,
        context=None, graph=lambda project: GRAPH if project == "tinyml" else None,
    )  # type: ignore[arg-type]  # fmt: skip
    read = {"command": f'graphify affected "chronological_split()" --graph {GRAPH}'}

    async def main() -> None:
        on = await chats.open("tinyml", tmp_path, "sonnet", "high", None)
        off = await chats.open("other", tmp_path, "sonnet", "high", None)
        assert await chats.ask(on.id, "Bash", read) == {"behavior": "allow"}
        asking = asyncio.create_task(chats.ask(on.id, "Bash", {"command": "ls"}))
        other = asyncio.create_task(chats.ask(off.id, "Bash", read))
        await asyncio.sleep(0.01)
        cards = [e for e in events if e.get("kind") == "permission"]
        assert [(e["id"], e["target"]) for e in cards] == [
            (on.id, "ls"), (off.id, read["command"])
        ]  # fmt: skip
        asking.cancel()
        other.cancel()

    asyncio.run(main())


OUT = FIXTURES / "out"  # graphify's output on the fixture graph (graphify 0.9.120, 2026-11-26)


def test_tool_line_of_a_graph_read() -> None:
    line = tool_line(
        "Bash", {"command": f'graphify affected "chronological_split()" --graph {GRAPH}'}
    )
    assert line == "Asked the graph: affected chronological_split()"
    line = tool_line(
        "Bash", {"command": f"graphify query 'what calls x' --graph {GRAPH} --depth 3"}
    )
    assert line == "Asked the graph: query what calls x --depth 3"
    assert tool_line("Bash", {"command": "graphify update ."}) == "Bash graphify update ."
    assert tool_line("Bash", {"command": 'graphify query "open'}) == 'Bash graphify query "open'


@pytest.mark.parametrize(
    ("sample", "ids"),
    [
        (
            "affected",
            ["src_test_combined_load_parts", "src_test_envelope_load1_split",
             "src_test_held_out_load_parts", "src_test_combined", "src_test_envelope",
             "src_test_held_out", "src_test_held_out_run"],
        ),
        (
            "explain",
            ["src_split_chronological_split", "src_test_combined", "src_test_envelope",
             "src_test_held_out", "src_test_held_out_load_parts", "src_split",
             "src_test_combined_load_parts", "src_test_envelope_load1_split"],
        ),
        ("path", ["src_test_envelope_load1_split", "src_split_chronological_split"]),
        (
            "query",  # 8 NODE lines: the docstring one is not in the parsed graph
            ["src_split_chronological_split", "src_split", "src_test_envelope_load1_split",
             "src_test_held_out_load_parts", "src_test_combined_load_parts", "numpy",
             "src_test_held_out_run"],
        ),
    ],
)  # fmt: skip
def test_node_ids_from_a_sample_output(sample: str, ids: list[str]) -> None:
    graph = read(FIXTURES / "graph.json")
    assert ids_in(graph, (OUT / f"{sample}.txt").read_text()) == ids


def test_nothing_from_an_error_or_another_output() -> None:
    graph = read(FIXTURES / "graph.json")
    assert ids_in(graph, "No node matching 'test_set()' found.") == []
    assert ids_in(graph, "- nowhere() [calls] src/x.py:L1\n") == []


def test_a_graph_read_result_carries_its_node_ids(tmp_path: Path, graphs: Path) -> None:
    events: list[dict] = []
    path = graphs / "demo" / "graph.json"
    chats = Chats(
        lambda on_event: FakeChat(on_event, delay=0), events.append, tmp_path,
        context=None, graph=lambda project: path,
    )  # type: ignore[arg-type]  # fmt: skip
    command = f'graphify affected "chronological_split()" --graph {path}'

    async def main() -> None:
        chat = await chats.open("demo", tmp_path, "sonnet", "high", None)
        chat.turns.append({"text": "what breaks?", "events": [], "done": False})
        for call, text in (("g", (OUT / "affected.txt").read_text()), ("l", "a.txt\n")):
            given = {"command": command} if call == "g" else {"command": "ls"}
            line = tool_line("Bash", given)
            await chats.on_event(
                chat.id, {"type": "tool", "id": call, "name": "Bash", "line": line}
            )
            await chats.on_event(
                chat.id, {"type": "tool_result", "id": call, "error": False, "text": text}
            )

    asyncio.run(main())
    graph_result, ls_result = [e for e in events if e["kind"] == "tool_result"]
    assert graph_result["nodes"][:2] == [
        "src_test_combined_load_parts",
        "src_test_envelope_load1_split",
    ]
    assert "nodes" not in ls_result


def test_adding_a_doc_costs_tokens_and_is_kept_in_project_md(vault: Path, graphs: Path) -> None:
    project_md = vault / "projects" / "demo" / "project.md"
    save_graph(project_md, True)
    ctx = asyncio.run(make(vault, graphs).context("demo", None, None))
    assert "costs tokens" in ctx.text and "wait for his yes" in ctx.text
    assert f"`graph_docs:` list in {project_md}" in ctx.text
    assert "The graph holds code only. " in ctx.text

    text = project_md.read_text().replace("---\nDemo", "graph_docs:\n  - README.md\n---\nDemo")
    project_md.write_text(text)
    save_graph(project_md, True)  # hubd's own writes keep the list
    assert project_md.read_text() == text
    ctx = asyncio.run(make(vault, graphs).context("demo", None, None))
    assert "The graph holds code only, plus these docs: README.md." in ctx.text
