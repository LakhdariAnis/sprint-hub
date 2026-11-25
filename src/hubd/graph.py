"""The one interface hubd uses for code graphs (docs/ROADMAP.md rule 4, ADR 0004).

`GraphifyGraph` shells out to `graphify`; `FakeGraph` serves a fixed graph for tests and
`hubd --demo`.
Everything fails soft (rule 4): no graph is `None` (or empty) plus a reason, never an exception.
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class Node:
    id: str
    label: str
    file: str  # "" for a library the code imports
    line: int | None
    group: int | None  # graphify's community
    group_name: str
    degree: int


@dataclass(frozen=True)
class Link:
    source: str
    target: str
    relation: str  # calls, imports, imports_from, contains, …


@dataclass(frozen=True)
class Graph:
    nodes: list[Node]
    links: list[Link]
    groups: dict[int, str]
    commit: str | None  # the repo commit graphify read
    built_at: str  # ISO time graph.json was written


@dataclass(frozen=True)
class Built:
    """What a build gave: the graph's size, or why there is none."""

    nodes: int = 0
    links: int = 0
    reason: str | None = None


class GraphError(ValueError):
    """graph.json is not in the shape this parser knows: the message is the reason."""


class GraphSource(Protocol):
    def build(self, project_path: str | Path, project: str | None = None) -> Built:
        """Build or refresh the graph of a repo; `project` names it (default: the folder name)."""
        ...

    def load(self, project: str) -> Graph | None: ...

    def affected(self, project: str, node: str, depth: int = 2) -> list[tuple[str, str]]:
        """The node ids that break if `node` changes, each with the relation that reaches it."""
        ...

    def path(self, project: str, a: str, b: str) -> list[str]:
        """The node ids from `a` to `b` in order; [] when they are not connected."""
        ...

    def report(self, project: str) -> str:
        """graphify's GRAPH_REPORT.md, "" when there is none."""
        ...

    def reason(self, project: str) -> str | None:
        """Why the last call for this project gave nothing; None when it went fine."""
        ...


# Docstrings graphify keeps as nodes: text, not code.
DOCSTRING = "rationale"


def parse(data: object, built_at: str) -> Graph:
    """graphify's graph.json as a `Graph`. New fields are ignored, a missing one raises."""
    try:
        raw_nodes = [n for n in data["nodes"] if n.get("file_type") != DOCSTRING]
        ids = {n["id"] for n in raw_nodes}
        links = [
            Link(str(e["source"]), str(e["target"]), str(e["relation"]))
            for e in data["links"]
            if e["source"] in ids and e["target"] in ids
        ]
        degree = dict.fromkeys(ids, 0)
        for link in links:
            degree[link.source] += 1
            degree[link.target] += 1
        nodes = [
            Node(
                id=str(n["id"]),
                label=str(n["label"]),
                file=n.get("source_file") or "",
                line=_line(n.get("source_location")),
                group=n.get("community"),
                group_name=n.get("community_name") or "",
                degree=degree[n["id"]],
            )
            for n in raw_nodes
        ]
        commit = data.get("built_at_commit")
    except (KeyError, TypeError, AttributeError) as exc:
        raise GraphError(f"graph.json has no field {exc}") from exc
    groups = {n.group: n.group_name for n in nodes if n.group is not None}
    return Graph(nodes, links, dict(sorted(groups.items())), commit, built_at)


def read(path: Path) -> Graph:
    """Parse a graph.json file; raises `GraphError` with the reason."""
    try:
        data = json.loads(path.read_text())
        built_at = datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat(timespec="seconds")
    except FileNotFoundError as exc:
        raise GraphError("no graph built yet") from exc
    except (OSError, ValueError) as exc:
        raise GraphError(f"cannot read {path}: {exc}") from exc
    return parse(data, built_at)


def _line(location: object) -> int | None:
    """graphify's "L17" as 17."""
    text = str(location or "")
    return int(text[1:]) if text[:1] == "L" and text[1:].isdigit() else None
