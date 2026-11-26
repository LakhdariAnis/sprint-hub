"""What a chat started from a project, a sprint or a step knows: built from the repo's files.

hubd passes it to claude with `--append-system-prompt`; the page only shows its size.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

from hubd.graph import Graph
from hubd.vault import live_file

CAP = 40_000  # bytes; one argv string may be at most 128 KiB (Linux MAX_ARG_STRLEN)
README_LINES = 200


@dataclass
class Context:
    text: str = ""
    parts: list[str] = field(default_factory=list)  # what was loaded, for the chip
    notes: list[str] = field(default_factory=list)  # what was missing

    def json(self) -> dict:
        size = len(self.text.encode())
        return {"label": " + ".join(self.parts), "size": size, "notes": self.notes}


def cap(text: str, limit: int = CAP) -> str:
    """Whole lines up to `limit` bytes, then `[cut: N lines]`."""
    if len(text.encode()) <= limit:
        return text
    lines, kept, size = text.split("\n"), [], 0
    for line in lines:
        size += len(line.encode()) + 1
        if size > limit - 32:  # room for the note
            break
        kept.append(line)
    return "\n".join([*kept, f"[cut: {len(lines) - len(kept)} lines]"])


def _read(path: Path) -> str | None:
    return path.read_text(errors="replace") if path.is_file() else None


def _table(lines: list[str], heading: re.Pattern[str]) -> list[str]:
    """The first table under the first `## ` heading matching `heading`."""
    start = next((i for i, x in enumerate(lines) if heading.match(x)), None)
    table: list[str] = []
    for line in lines[start + 1 :] if start is not None else []:
        if line.startswith("## "):
            break
        if line.lstrip().startswith("|"):
            table.append(line)
        elif table:
            break
    return table


def _first_cell(row: str) -> str:
    return row.strip().strip("|").split("|")[0].strip().strip("`")


def _entries(progress: str, ids: set[str]) -> list[str]:
    """`## date — Step <id> …` entries of PROGRESS.md for these step ids, newest first."""
    blocks = re.split(r"(?m)^## ", progress)[1:]
    out = []
    for block in blocks:
        m = re.search(r"Step (\w+)", block.partition("\n")[0])
        if m and m[1].lower() in ids:
            out.append("## " + block.rstrip())
    return out


# The graphify commands a chat may run without a card (`hubd.permits.graph_read`).
GRAPH_READS = (
    ("query", '"<question>"'),
    ("path", '"<A>" "<B>"'),
    ("affected", '"<X>"'),
    ("explain", '"<X>"'),
)


def graph_block(path: Path, graph: Graph) -> str:
    """What a chat on a `graph: on` project is told of its code graph (657)."""
    commit = graph.commit[:7] if graph.commit else "unknown"
    lines = [
        "## Code graph",
        f"A graphify code graph of this repo is at {path}: {len(graph.nodes)} nodes, "
        f"{len(graph.links)} links, built from commit {commit} at {graph.built_at}.",
        "Prefer these for structure questions (what calls X, what breaks if X changes, how X "
        "and Y are connected, what X is) over reading many files: they are faster and cheaper, "
        "and they run without asking Anis because they only read.",
        *(f"- `graphify {verb} {args} --graph {path}`" for verb, args in GRAPH_READS),
        "Name a node by its label, e.g. `split.py` or `main()`. Run each as one plain command "
        "with that `--graph`: no pipes, `&&`, `;`, redirects or `$`, or it needs Anis's OK.",
        "",
    ]
    return "\n".join(lines)


class _Builder:
    def __init__(self, repo: Path):
        self.repo = repo
        self.ctx = Context()
        self.out: list[str] = []

    def add(self, title: str, body: str | None, part: str | None, missing: str) -> None:
        """A section, or a short `[missing]` note in its place."""
        if body and body.strip():  # strip("\n"): a diffstat line starts with a space
            self.out += [f"### {title}", body.strip("\n").rstrip(), ""]
            if part:
                self.ctx.parts.append(part)
        else:
            self.out += [f"### {title}", f"[{missing}]", ""]
            if missing not in self.ctx.notes:
                self.ctx.notes.append(missing)


def build(
    repo: Path,
    name: str,
    sprint: int | None = None,
    step: str | None = None,
    spec: str | None = None,
    diffstat: str | None = None,
    graph: str | None = None,
) -> Context:
    """The project's context, with the sprint's and the step's in front when given.

    Most specific first, so the cap cuts the README before the step. `spec` and `diffstat` come
    from the hub (the spec may be archived, the diffstat needs the step branch); None = none.
    `graph`: the `graph_block` of a `graph: on` project, kept first so the cap never cuts it.
    """
    b = _Builder(repo)
    b.out += [
        f"# sprint-hub context: project {name}",
        f"This chat was started from sprint-hub about project {name} (repo {repo}). The files "
        "below are what it loaded from the repo when the chat began: use them, do not ask what "
        "the project is.",
        "",
    ]
    if graph:
        b.out.append(graph)
    progress = _read(repo / "sprint/PROGRESS.md")
    readme = _read(repo / "sprint/README.md")
    lines = readme.split("\n") if readme is not None else []
    if step:
        b.out.append(f"## Step {step}")
        b.add("Spec", spec, "spec", f"no spec for step {step}")
        path = live_file(repo, "progress", step) or next(
            iter(sorted(repo.glob(f"sprint/archive/**/progress/{step}.md"))), None
        )
        b.add(
            f"Checklist (sprint/progress/{step}.md)",
            path and _read(path),
            "checklist",
            f"no sprint/progress/{step}.md",
        )
        report = _entries(progress, {step.lower()}) if progress else []
        b.add(
            "Report (sprint/PROGRESS.md)",
            "\n\n".join(report),
            "report",
            "no sprint/PROGRESS.md" if progress is None else f"no PROGRESS.md entry for {step}",
        )
        b.add(
            "Diffstat against base",
            diffstat,
            "diffstat",
            f"no diffstat: step {step} has no branch or git failed",
        )
    if sprint is not None:
        b.out.append(f"## Sprint {sprint}")
        if readme is None:
            b.add("Sprint row", None, None, "no sprint/README.md")
        else:
            rows = _table(lines, re.compile(r"## Sprints\s*$"))
            row = [r for r in rows[2:] if _first_cell(r) == str(sprint)]
            b.add(
                "Row of the Sprints table",
                "\n".join(rows[:2] + row) if row else None,
                f"sprint {sprint}",
                f"no row for sprint {sprint} in sprint/README.md",
            )
            steps = _table(lines, re.compile(rf"## Sprint {sprint}\b.*steps", re.I))
            b.add("Steps table", "\n".join(steps), "steps", f"no steps table for sprint {sprint}")
            ids = {_first_cell(r).lower() for r in steps[2:]}
            if progress is None:
                b.add("PROGRESS.md entries of its steps", None, None, "no sprint/PROGRESS.md")
            else:
                b.add(
                    "PROGRESS.md entries of its steps",
                    "\n\n".join(_entries(progress, ids)),
                    "progress",
                    f"no PROGRESS.md entries for sprint {sprint}",
                )
    b.out.append("## Project")
    head = _read(repo / "README.md")
    head = "\n".join(head.split("\n")[:README_LINES]) if head is not None else None
    b.add(f"README.md (first {README_LINES} lines)", head, "README", "no README.md")
    sprints = _table(lines, re.compile(r"## Sprints\s*$"))
    b.add(
        "Sprints (sprint/README.md)",
        "\n".join(sprints),
        "sprints",
        "no sprint/README.md" if readme is None else "no Sprints table in sprint/README.md",
    )
    if graph:
        b.ctx.parts.append("graph")
    b.ctx.text = cap("\n".join(b.out).rstrip() + "\n")
    return b.ctx
