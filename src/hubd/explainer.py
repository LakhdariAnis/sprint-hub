"""The project explainer: a lecture-handout page Claude writes once into the vault (660)."""

import asyncio
import json
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from hubd import permits
from hubd.importer import git
from hubd.runners.chat import ChatEvent, ChatRunner
from hubd.states import InvalidTransition
from hubd.vault import _write_atomic

# The page's 9 sections, in order: the Explainer tab (661) and Obsidian show them as they are.
SECTIONS = (
    "In one sentence",
    "The problem",
    "Big picture",
    "Stages",
    "Key ideas",
    "Results",
    "Weak spots",
    "How to run",
    "Glossary",
)
# The stages of each `type:` in project.md.
STAGES = {
    "ml": ("data", "windows / prep", "features", "split", "models", "shrink", "on the device"),
    "app": ("user", "screens", "API", "data"),
    "robotics": ("sensors", "nodes and topics", "control", "actuators"),
    "report": ("goal", "method", "results", "conclusion"),
}
KINDS = {
    "ml": "ML / embedded",
    "app": "app / web",
    "robotics": "robotics / ROS",
    "report": "school report / TP",
}
HEAD = "Write the explainer of project"  # FakeChat knows the explainer turn by it
FILE = "explainer.md"  # next to `project.md`
# The fenced blocks the Explainer tab draws, and the `|` cells of each line.
BLOCKS = {"stages": 5, "kpis": 2, "bars": 2}
WAIT = 20 * 60  # seconds the turn may take, then it is stopped and fails
TYPE_LINE = "type: "  # the first line of the answer when project.md has no `type:`


def _stages(kind: str) -> str:
    extra = " Give one flow per main feature." if kind == "app" else ""
    return f"{kind} ({KINDS[kind]}): " + " → ".join(STAGES[kind]) + "." + extra


def prompt(name: str, kind: str | None) -> str:
    """The fixed explainer prompt. `kind` None: Claude picks the type and says which first."""
    if kind is None:
        stages = [
            f"project.md has no `type:`. Pick the type that fits best and make the very first "
            f"line of your answer `{TYPE_LINE}<type>` (one of {', '.join(STAGES)}), then the page. "
            "The Stages section follows the stages of that type:",
            *(f"- {_stages(k)}" for k in STAGES),
        ]
    else:
        stages = [f"The Stages section follows these stages: {_stages(kind)}"]
    return "\n".join(
        [
            f"{HEAD} {name}: a page that teaches it like a lecture handout, for someone who "
            "knows programming but not this project. Read the README, the code and the code "
            "graph if there is one. Only read: write no file and run nothing else.",
            "",
            "Answer with the page only, as plain markdown (no frontmatter, no preamble), with "
            "exactly these `## ` headings, in this order:",
            *(f"{i}. {s}" for i, s in enumerate(SECTIONS, 1)),
            "",
            *stages,
            "",
            "In the Stages section, after a short paragraph per stage, put one fenced block:",
            "```stages",
            "<stage name> | <what goes in> | <what comes out> | <its numbers> | <its files>",
            "```",
            "one line per stage. Under In one sentence, put the 3 or 4 numbers that matter most:",
            "```kpis",
            "<value> | <label>",
            "```",
            "Under Results, the results worth comparing as bars (value: a plain number):",
            "```bars",
            "<label> | <value>",
            "```",
            "",
            "Rules: plain words, short sentences, explain every term once (in the Glossary too). "
            "Every number comes from the README or the code: never invent, round or guess one; "
            "leave a number out when you cannot find it. File, function and command names go in "
            "inline code, e.g. `split.py` or `main()`. Weak spots: what is missing, fragile or "
            "untested, from the code. How to run: the real commands from the README.",
        ]
    )


def blocks(text: str) -> dict[str, list[list[str]]]:
    """The lines of each ```stages, ```kpis and ```bars block, split into stripped cells."""
    found: dict[str, list[list[str]]] = {}
    for name, body in re.findall(r"(?ms)^```(stages|kpis|bars)[ \t]*\n(.*?)^```", text):
        rows = [[c.strip() for c in line.split("|")] for line in body.splitlines() if line.strip()]
        found.setdefault(name, []).extend(rows)
    return found


def problems(text: str) -> list[str]:
    """What the page gets wrong against the prompt: headings, blocks, cells. Empty: none."""
    out = []
    if (headings := re.findall(r"(?m)^## (.+?)\s*$", text)) != list(SECTIONS):
        out.append(f"headings are {headings}, not the 9 sections in order")
    found = blocks(text)
    for name, cells in BLOCKS.items():
        rows = found.get(name)
        if not rows:
            out.append(f"no ```{name} block")
        out += [
            f"{name}: {' | '.join(r)} has not {cells} cells" for r in rows or [] if len(r) != cells
        ]
    for row in found.get("bars", []):
        if len(row) == 2 and not re.fullmatch(r"-?\d+(\.\d+)?", row[1]):
            out.append(f"bars: {row[1]} is not a plain number")
    return out


@dataclass
class Page:
    kind: str | None  # the project's type, or the one Claude picked
    guessed: bool
    body: str


def page(answer: str, kind: str | None) -> Page:
    """Claude's answer as a page: the `type:` line read off when it had to guess."""
    guessed = kind is None
    if guessed and (m := re.match(rf"\s*{TYPE_LINE}(\w+)", answer)):
        kind = m[1] if m[1] in STAGES else None
    start = answer.find("## ")  # a stray line of preamble before the first heading goes
    return Page(kind, guessed, answer[start:] if start >= 0 else answer.strip())


def write(
    folder: Path, p: Page, written: str, commit: str | None, model: str | None, cost: float | None
) -> Path:
    """`explainer.md` in the project's vault folder, frontmatter first."""
    # A commit of only digits would read back as a number: quoted.
    sha = json.dumps(commit) if commit else None
    meta = {"written": written, "commit": sha, "model": model, "type": p.kind, "cost": cost}
    head = ["---", *(f"{k}: {'' if v is None else v}" for k, v in meta.items())]
    if p.guessed:
        head.append("guessed: true")
    head.append("---")
    if p.guessed:
        head.append(
            f"> Type guessed by Claude: {p.kind or 'none fits'}. Set `type:` in "
            "project.md to change it.\n"
        )
    path = folder / FILE
    _write_atomic(path, ("\n".join(head) + "\n" + p.body.rstrip() + "\n").encode())
    return path


@dataclass
class _Job:
    project: str
    graph: Path | None  # its graph.json: graphify reads of it need no OK
    text: list[str] = field(default_factory=list)
    end: dict[str, Any] = field(default_factory=dict)  # the `turn_end` event
    error: str | None = None
    done: asyncio.Event = field(default_factory=asyncio.Event)


class Explainers:
    """One headless Claude turn per explainer, one at a time per project. Events: `emit`."""

    def __init__(self, chat: Callable[[ChatEvent], ChatRunner], emit: Callable[[dict], None]):
        self.runner = chat(self.on_event)
        self.runner.ask = self.ask
        self.emit = emit
        self.jobs: dict[str, _Job] = {}  # chat id -> the explainer it writes
        self.tasks: dict[str, asyncio.Task[None]] = {}  # project -> its turn

    def start(
        self,
        project: str,
        repo: Path,
        folder: Path,
        model: str,
        kind: str | None,
        system: str | None,
        graph: Path | None,
        account: str = "claude",
    ) -> None:
        """Write `folder/explainer.md` in the background. InvalidTransition: one runs already."""
        if project in self.tasks:
            raise InvalidTransition(f"an explainer of {project} is being written")
        chat_id = str(uuid.uuid4())
        self.jobs[chat_id] = job = _Job(project, graph)
        run = self._run(chat_id, job, repo, folder, model, kind, system, account)
        self.tasks[project] = asyncio.create_task(run)

    async def _run(
        self,
        chat_id: str,
        job: _Job,
        repo: Path,
        folder: Path,
        model: str,
        kind: str | None,
        system: str | None,
        account: str,
    ) -> None:
        self.emit({"type": "explainer_started", "project": job.project})
        try:
            await self.runner.open(chat_id, repo, model, None, system, account=account)
            await self.runner.send(chat_id, prompt(job.project, kind))
            try:
                await asyncio.wait_for(job.done.wait(), WAIT)
            except TimeoutError:
                job.error = f"no answer in {WAIT // 60} minutes"
            if job.error:
                self.emit({"type": "explainer_failed", "project": job.project, "reason": job.error})
                return
            text = "".join(job.text)
            commit = await asyncio.to_thread(git, repo, "rev-parse", "HEAD")
            written = datetime.now(UTC).isoformat(timespec="seconds")
            cost = job.end.get("cost_usd")
            p = page(text, kind)
            path = await asyncio.to_thread(
                write, folder, p, written, commit or None, job.end.get("model"), cost
            )
            self.emit(
                {
                    "type": "explainer_done",
                    "project": job.project,
                    "path": str(path),
                    "cost_usd": cost,
                    "problems": problems(p.body),
                }
            )
        finally:
            await self.runner.close(chat_id)
            del self.jobs[chat_id], self.tasks[job.project]

    async def on_event(self, chat_id: str, event: dict[str, Any]) -> None:
        if (job := self.jobs.get(chat_id)) is None:
            return
        kind = event["type"]
        if kind == "text":
            job.text.append(event["text"])
        elif kind == "tool":
            self.emit({"type": "explainer_progress", "project": job.project, "line": event["line"]})
        elif kind == "error":
            job.error = event["message"]
            job.done.set()
        elif kind == "turn_end":
            job.end = event
            job.done.set()

    async def ask(self, chat_id: str, tool: str, tool_input: dict[str, Any]) -> dict[str, str]:
        """Only graphify reads of the project's graph: the explainer writes and runs nothing."""
        job = self.jobs.get(chat_id)
        if job and permits.graph_read(tool, tool_input, job.graph):
            return {"behavior": "allow"}
        return {"behavior": "deny", "message": "The explainer only reads: write and run nothing."}

    async def close_all(self) -> None:
        for task in list(self.tasks.values()):
            task.cancel()
        await asyncio.gather(*self.tasks.values(), return_exceptions=True)
