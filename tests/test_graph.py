"""Contract: the parser maps a real graphify graph.json (tinyml-bearing-fault, graphify 0.9.120)."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from hubd.graph import Built, GraphError, GraphifyGraph, parse, read

FIXTURE = Path(__file__).parent / "fixtures" / "graphify" / "graph.json"
RAW = json.loads(FIXTURE.read_text())


def test_fixture_parses_to_nodes_links_groups_and_commit() -> None:
    graph = read(FIXTURE)
    split = next(n for n in graph.nodes if n.id == "src_split_chronological_split")
    assert (split.label, split.file, split.line) == ("chronological_split()", "src/split.py", 3)
    assert split.degree == sum(split.id in (e.source, e.target) for e in graph.links) > 0
    assert graph.groups[split.group] == split.group_name
    assert graph.commit == RAW["built_at_commit"]
    assert graph.built_at
    numpy = next(n for n in graph.nodes if n.id == "numpy")
    assert numpy.file == "" and numpy.line is None


def test_docstring_nodes_and_their_links_are_dropped() -> None:
    graph = read(FIXTURE)
    docstrings = {n["id"] for n in RAW["nodes"] if n.get("file_type") == "rationale"}
    assert docstrings
    assert not docstrings & {n.id for n in graph.nodes}
    assert len(graph.nodes) == len(RAW["nodes"]) - len(docstrings)
    assert "rationale_for" not in {e.relation for e in graph.links}


def test_a_field_graphify_adds_later_is_ignored() -> None:
    data = json.loads(FIXTURE.read_text())
    data["new_top"] = 1
    for item in data["nodes"] + data["links"]:
        item["new_field"] = {"x": 1}
    assert parse(data, "t") == parse(RAW, "t")


def test_a_missing_field_is_a_reason() -> None:
    data = json.loads(FIXTURE.read_text())
    del data["nodes"][0]["label"]
    with pytest.raises(GraphError, match="no field 'label'"):
        parse(data, "t")


def test_a_missing_or_broken_file_is_a_reason(tmp_path: Path) -> None:
    with pytest.raises(GraphError, match="no graph built yet"):
        read(tmp_path / "graph.json")
    (tmp_path / "graph.json").write_text("{not json")
    with pytest.raises(GraphError, match="cannot read"):
        read(tmp_path / "graph.json")


def repo(tmp_path: Path) -> Path:
    """A tiny git repo with two Python files, one calling the other."""
    path = tmp_path / "tiny"
    (path / "src").mkdir(parents=True)
    (path / "src" / "a.py").write_text('def helper():\n    """Help."""\n    return 1\n')
    (path / "src" / "b.py").write_text("from a import helper\n\n\ndef main():\n    helper()\n")
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(path), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "x"],
        check=True,
    )
    return path


def fake_graphify(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: str) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "graphify").write_text(f"#!/bin/sh\n{body}\n")
    (bin_dir / "graphify").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:/usr/bin:/bin")


def test_missing_graphify_is_a_reason(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))
    source = GraphifyGraph(tmp_path / "graphs")
    assert source.build(tmp_path) == Built(reason="graphify not on PATH")
    assert source.reason(tmp_path.name) == "graphify not on PATH"


def test_a_crash_is_a_reason(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_graphify(tmp_path, monkeypatch, "echo boom >&2; exit 2")
    built = GraphifyGraph(tmp_path / "graphs").build(tmp_path, "p")
    assert built == Built(reason="graphify update failed (2): boom")


def test_a_graph_in_an_unknown_shape_is_a_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_graphify(tmp_path, monkeypatch, 'echo \'{"vertices": []}\' > "$GRAPHIFY_OUT/graph.json"')
    source = GraphifyGraph(tmp_path / "graphs")
    assert source.build(tmp_path, "p") == Built(reason="graph.json has no field 'nodes'")
    assert source.load("p") is None
    assert source.reason("p") == "graph.json has no field 'nodes'"


def test_no_graph_yet_is_a_reason(tmp_path: Path) -> None:
    source = GraphifyGraph(tmp_path)
    assert source.load("p") is None and source.reason("p") == "no graph built yet"
    assert source.report("p") == "" and source.reason("p") == "no graph report built yet"


@pytest.mark.skipif(shutil.which("graphify") is None, reason="graphify is not installed")
def test_a_real_build_leaves_the_repo_clean(tmp_path: Path) -> None:
    path = repo(tmp_path)
    source = GraphifyGraph(tmp_path / "graphs")
    built = source.build(path)
    assert built.reason is None and built.nodes > 0, source.reason("tiny")
    assert not (path / "graphify-out").exists()
    status = subprocess.run(["git", "-C", str(path), "status", "--porcelain"], capture_output=True)
    assert status.stdout == b""
    graph = source.load("tiny")
    assert graph is not None and "main()" in {n.label for n in graph.nodes}
    assert source.report("tiny").startswith("# Graph Report")


def fixture_source(tmp_path: Path) -> GraphifyGraph:
    """A GraphifyGraph whose project "p" holds the fixture graph."""
    (tmp_path / "graphs" / "p").mkdir(parents=True)
    shutil.copy(FIXTURE, tmp_path / "graphs" / "p" / "graph.json")
    return GraphifyGraph(tmp_path / "graphs")


@pytest.mark.skipif(shutil.which("graphify") is None, reason="graphify is not installed")
def test_affected_and_path_map_graphify_back_to_node_ids(tmp_path: Path) -> None:
    source = fixture_source(tmp_path)
    affected = dict(source.affected("p", "src_split_chronological_split"))
    assert affected["src_test_held_out_load_parts"] == "calls"
    assert affected["src_test_held_out"] == "imports"
    assert len(affected) == 7
    recipe, envelope = "src_test_held_out_recipe", "src_envelope_features_extract_envelope_features"
    assert source.path("p", recipe, envelope) == [recipe, envelope]
    split = "src_split_chronological_split"
    assert source.path("p", recipe, split) == [recipe, "src_test_held_out", split]
    assert source.reason("p") is None


def test_an_unknown_node_is_a_reason(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = fixture_source(tmp_path)
    fake_graphify(tmp_path, monkeypatch, "echo 'No unique node match for nope'; exit 4")
    assert source.affected("p", "nope") == []
    assert source.reason("p") == "No unique node match for nope"
    assert source.path("p", "nope", "numpy") == []


def test_no_path_is_an_empty_list(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = fixture_source(tmp_path)
    fake_graphify(tmp_path, monkeypatch, "echo \"No path found between 'a' and 'b'.\"")
    assert source.path("p", "a", "b") == []
