"""The one interface hubd uses for code graphs (docs/ROADMAP.md rule 4, ADR 0004).

`GraphifyGraph` shells out to `graphify`; `FakeGraph` serves a fixed graph for tests and
`hubd --demo`.
Everything fails soft (rule 4): no graph is `None` (or empty) plus a reason, never an exception.
"""

import json
import os
import re
import shutil
import subprocess
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


GRAPHS = Path.home() / ".local" / "share" / "sprint-hub" / "graphs"
TIMEOUT = 120  # seconds; tinyml (33 code files) takes 1.5 s
# `graphify affected`: "- load_parts() [calls] src/test_held_out.py:L31" (the line is the edge's).
AFFECTED = re.compile(r"^- (.+) \[(\w+)\](?: (.+?)(?::L\d+)?)?$")
# `graphify path`: "recipe() <--indirect_call [INFERRED 0.85]-- t.py --imports [EXTRACTED]--> x()"
HOP = re.compile(r" (?:<--\S+ \[[^\]]*\]--|--\S+ \[[^\]]*\]-->) ")


class GraphifyGraph:
    """The real `GraphSource`: `graphify update` (code only, no LLM), one folder per project.

    graphify writes into `<repo>/graphify-out/` unless `GRAPHIFY_OUT` names another folder,
    so the repo stays clean. `build` blocks up to 2 min: call it with `asyncio.to_thread`.
    """

    def __init__(self, root: Path = GRAPHS, exe: str = "graphify") -> None:
        self.root, self.exe = root, exe
        self._reasons: dict[str, str | None] = {}

    def _out(self, project: str) -> Path:
        return self.root / project

    def _cli(self, project: str, *args: str) -> subprocess.CompletedProcess[str] | None:
        """Run graphify with its output in the project's folder; None (and a reason) if it fails."""
        exe = shutil.which(self.exe)
        if exe is None:
            self._reasons[project] = f"{self.exe} not on PATH"
            return None
        out = self._out(project)
        out.mkdir(parents=True, exist_ok=True)
        try:
            done = subprocess.run(
                [exe, *args],
                cwd=out,
                env={**os.environ, "GRAPHIFY_OUT": str(out)},
                capture_output=True,
                text=True,
                timeout=TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            self._reasons[project] = f"graphify {args[0]} took over {TIMEOUT // 60} min"
            return None
        except OSError as exc:
            self._reasons[project] = f"graphify does not run: {exc}"
            return None
        self._reasons[project] = None
        return done

    def build(self, project_path: str | Path, project: str | None = None) -> Built:
        repo = Path(project_path).expanduser()
        name = project or repo.name
        if not repo.is_dir():
            self._reasons[name] = f"{repo} is not a folder"
            return Built(reason=self._reasons[name])
        # --force: a rebuild with fewer nodes (code was deleted) still replaces the old graph.
        done = self._cli(name, "update", str(repo), "--force")
        if done is not None and done.returncode != 0:
            lines = (done.stderr or done.stdout).strip().splitlines() or ["no output"]
            self._reasons[name] = f"graphify update failed ({done.returncode}): {lines[-1]}"
        if self._reasons[name] is not None:
            return Built(reason=self._reasons[name])
        graph = self.load(name)
        if graph is None:
            return Built(reason=self._reasons[name])
        return Built(len(graph.nodes), len(graph.links))

    def load(self, project: str) -> Graph | None:
        try:
            graph = read(self._out(project) / "graph.json")
        except GraphError as exc:
            self._reasons[project] = str(exc)
            return None
        self._reasons[project] = None
        return graph

    def _query(self, project: str, *args: str) -> tuple[Graph, list[str]] | None:
        """Run a graphify query on the project's graph: the graph and graphify's output lines."""
        graph = self.load(project)
        if graph is None:
            return None
        done = self._cli(project, *args, "--graph", str(self._out(project) / "graph.json"))
        if done is None:
            return None
        lines = done.stdout.splitlines()
        if done.returncode != 0:  # 3: the name is ambiguous, 4: no such node
            self._reasons[project] = (lines or [f"graphify {args[0]} failed"])[0]
            return None
        return graph, lines

    def affected(self, project: str, node: str, depth: int = 2) -> list[tuple[str, str]]:
        found = self._query(project, "affected", node, "--depth", str(depth))
        if found is None:
            return []
        graph, lines = found
        ids = {(n.label, n.file): n.id for n in graph.nodes}
        result: dict[str, str] = {}
        for line in lines:
            if (m := AFFECTED.match(line)) and (key := (m[1], m[3] or "")) in ids:
                result.setdefault(ids[key], m[2])
        return list(result.items())

    def path(self, project: str, a: str, b: str) -> list[str]:
        found = self._query(project, "path", a, b, "--undirected")
        if found is None:
            return []
        graph, lines = found
        if len(lines) < 2 or not lines[0].startswith("Shortest path"):
            return []  # "No path found between …"
        labels = {n.id: n.label for n in graph.nodes}
        near: dict[str, list[str]] = {}
        for link in graph.links:
            near.setdefault(link.source, []).append(link.target)
            near.setdefault(link.target, []).append(link.source)
        # graphify prints labels; walk from `a` to the neighbour with each next label.
        ids = [a]
        for label in HOP.split(lines[1].strip())[1:]:
            step = next((n for n in near.get(ids[-1], []) if labels.get(n) == label), None)
            if step is None:
                self._reasons[project] = f"cannot follow graphify's path at {label}"
                return []
            ids.append(step)
        return ids if ids[-1] == b else []

    def report(self, project: str) -> str:
        try:
            return (self._out(project) / "GRAPH_REPORT.md").read_text()
        except OSError:
            self._reasons[project] = "no graph report built yet"
            return ""

    def reason(self, project: str) -> str | None:
        return self._reasons.get(project)


# The demo project's code (`hubd --demo`): (id, label, file, line, group),
# then (source, target, relation).
FAKE_NODES = [
    ("src_api", "api.py", "src/api.py", 1, 0),
    ("src_api_serve", "serve()", "src/api.py", 8, 0),
    ("src_api_list_items", "list_items()", "src/api.py", 14, 0),
    ("src_ui", "ui.py", "src/ui.py", 1, 1),
    ("src_ui_draw_list", "draw_list()", "src/ui.py", 5, 1),
    ("src_ui_sort_items", "sort_items()", "src/ui.py", 12, 1),
    ("src_store", "store.py", "src/store.py", 1, 2),
    ("src_store_load", "load()", "src/store.py", 4, 2),
    ("src_store_save", "save()", "src/store.py", 10, 2),
    ("fastapi", "fastapi", "", None, 0),
]
FAKE_LINKS = [
    ("src_api", "src_api_serve", "contains"),
    ("src_api", "src_api_list_items", "contains"),
    ("src_ui", "src_ui_draw_list", "contains"),
    ("src_ui", "src_ui_sort_items", "contains"),
    ("src_store", "src_store_load", "contains"),
    ("src_store", "src_store_save", "contains"),
    ("src_api", "fastapi", "imports"),
    ("src_api", "src_store", "imports_from"),
    ("src_ui", "src_api", "imports_from"),
    ("src_api_serve", "src_api_list_items", "calls"),
    ("src_api_list_items", "src_store_load", "calls"),
    ("src_ui_draw_list", "src_api_list_items", "calls"),
    ("src_ui_draw_list", "src_ui_sort_items", "calls"),
]
FAKE_GROUPS = {0: "api", 1: "ui", 2: "store"}
FAKE_REPORT = "# Graph Report - demo\n\n## God Nodes\n1. `list_items()` - 4 edges\n"


class FakeGraph:
    """A fixed graph for tests and `hubd --demo`: no graphify, the same graph for every project."""

    def __init__(self) -> None:
        data = {
            "nodes": [
                {"id": i, "label": label, "source_file": f, "source_location": line and f"L{line}",
                 "community": g, "community_name": FAKE_GROUPS[g]}
                for i, label, f, line, g in FAKE_NODES
            ],
            "links": [{"source": s, "target": t, "relation": r} for s, t, r in FAKE_LINKS],
            "built_at_commit": None,
        }  # fmt: skip
        self.graph = parse(data, "2026-11-25T09:00:00+00:00")

    def build(self, project_path: str | Path, project: str | None = None) -> Built:
        return Built(len(self.graph.nodes), len(self.graph.links))

    def load(self, project: str) -> Graph | None:
        return self.graph

    def affected(self, project: str, node: str, depth: int = 2) -> list[tuple[str, str]]:
        found: dict[str, str] = {}
        level = {node}
        for _ in range(depth):
            reached = {}
            for e in self.graph.links:
                if e.target in level and e.source != node and e.source not in found:
                    reached.setdefault(e.source, e.relation)
            found |= reached
            level = set(reached)
        return list(found.items())

    def path(self, project: str, a: str, b: str) -> list[str]:
        came: dict[str, str | None] = {a: None}
        queue = [a]
        for here in queue:
            if here == b:
                ids = [b]
                while (prev := came[ids[-1]]) is not None:
                    ids.append(prev)
                return ids[::-1]
            for e in self.graph.links:
                for x, y in ((e.source, e.target), (e.target, e.source)):
                    if x == here and y not in came:
                        came[y] = here
                        queue.append(y)
        return []

    def report(self, project: str) -> str:
        return FAKE_REPORT

    def reason(self, project: str) -> str | None:
        return None
