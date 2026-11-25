"""Contract: the parser maps a real graphify graph.json (tinyml-bearing-fault, graphify 0.9.120)."""

import json
from pathlib import Path

import pytest

from hubd.graph import GraphError, parse, read

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
