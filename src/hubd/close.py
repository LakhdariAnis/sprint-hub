"""Close a sprint like the `new-sprint` skill's flow E: plan it (no writes), then write it.

Repo files only: the vault's `sprint:` lines are the daemon's to write.
"""

import re
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path

from hubd.importer import git
from hubd.model import State
from hubd.states import InvalidTransition
from hubd.vault import StepEntry, _write_atomic, add_on_top
from hubd.weeks import Sprint, _cells, calibration

_ENTRY = re.compile(r"^## .*— Step (\w+)")
_TIME = re.compile(r"^Time: (\d+(?:\.\d+)?) h")


@dataclass
class Closed:
    project: str
    sprint: int
    planned: float | None
    hours: dict[str, float]  # step id -> its `Time:` hours
    no_time: list[str]  # steps with no `Time:` line, counted 0
    own_hours: float | None  # Anis's time not tied to a step
    actual: float
    moved: list[str]  # unfinished steps, to sprint `next`
    next: int
    next_status: str | None  # the next row's status after the close; None: no row
    factor: float
    factor_sprints: int
    factor_from: str


def step_times(progress: str) -> dict[str, float]:
    """Hours of each step's newest `Time:` line in `sprint/PROGRESS.md` (newest entry on top)."""
    times: dict[str, float] = {}
    step = None
    for line in progress.splitlines():
        if line.startswith("## "):
            step = m[1] if (m := _ENTRY.match(line)) else None
        elif step and step not in times and (m := _TIME.match(line)):
            times[step] = float(m[1])
    return times


def plan(
    repo: Path,
    project: str,
    number: int,
    own_hours: float | None,
    steps: list[StepEntry],
    tables: dict[str, list[Sprint]],
) -> Closed:
    """What closing sprint `number` writes; refuses (InvalidTransition) what it must not write."""
    rows = {s.number: s for s in tables.get(project, [])}
    if (sprint := rows.get(number)) is None:
        raise InvalidTransition(f"no Sprint {number} row in sprint/README.md")
    if sprint.status == "closed":
        raise InvalidTransition(f"Sprint {number} is already closed")
    if git(repo, "ls-files", "sprint"):
        raise InvalidTransition("sprint/ is tracked by git, close the sprint by hand")
    entries = [e for e in steps if e.project == project and e.step.sprint == number]
    entries.sort(key=lambda e: _id_key(e.step.step))
    mine = [e.step.step for e in entries]
    moved = [e.step.step for e in entries if e.step.state != State.approved]
    nxt = rows.get(number + 1)
    if moved and nxt is None:
        raise InvalidTransition(
            f"Sprint {number + 1} has no row in sprint/README.md: add it first,"
            " hubd never invents a sprint row"
        )
    if moved and nxt and nxt.status == "closed":
        raise InvalidTransition(f"Sprint {number + 1} is closed, its row can't take moved steps")
    path = repo / "sprint" / "PROGRESS.md"
    times = step_times(path.read_text()) if path.is_file() else {}
    hours = {i: times[i] for i in mine if i in times}
    actual = round(sum(hours.values()) + (own_hours or 0), 2)
    after = replace(sprint, actual=actual, status="closed")
    table = [after if s.number == number else s for s in tables[project]]
    factor, used, source = calibration(project, {**tables, project: table})
    return Closed(
        project=project,
        sprint=number,
        planned=sprint.planned,
        hours=hours,
        no_time=[i for i in mine if i not in times],
        own_hours=own_hours,
        actual=actual,
        moved=moved,
        next=number + 1,
        next_status=None if nxt is None else _next_status(repo, number, nxt.status),
        factor=round(factor, 2),
        factor_sprints=used,
        factor_from=source,
    )


def write(repo: Path, closed: Closed, today: date) -> None:
    """The README row's Actual and Status (and the next row's Status), then the PROGRESS entry."""
    path = repo / "sprint" / "README.md"
    lines = path.read_bytes().decode().split("\n")
    head, at = _table(lines)
    row = at[str(closed.sprint)]
    lines[row] = _set_cell(lines[row], head.index("actual"), f"{closed.actual:.1f} h")
    lines[row] = _set_cell(lines[row], head.index("status"), "closed")
    if closed.next_status == "current" and (nxt := at.get(str(closed.next))) is not None:
        lines[nxt] = _set_cell(lines[nxt], head.index("status"), "current")
    _write_atomic(path, "\n".join(lines).encode())

    path = repo / "sprint" / "PROGRESS.md"
    lines = path.read_text().split("\n") if path.is_file() else []
    add_on_top(lines, _entry(closed, today))
    _write_atomic(path, "\n".join(lines).encode())


def _entry(c: Closed, today: date) -> list[str]:
    planned = f"{c.planned:g} h" if c.planned is not None else "not set"
    own = "not recorded" if c.own_hours is None else f"{c.own_hours:g} h"
    steps = round(sum(c.hours.values()), 2)
    lines = [
        f"## {today} — Sprint {c.sprint} closed",
        "",
        f"- Planned {planned}, actual {c.actual:g} h (steps {steps:g} h, Anis's own {own}).",
    ]
    if c.no_time:
        lines.append(f"- No `Time:` line, counted 0: {', '.join(c.no_time)}.")
    moved = ", ".join(c.moved) if c.moved else "none"
    lines.append(f"- Moved to Sprint {c.next}: {moved}.")
    used = "no closed sprint"
    if c.factor_sprints:
        used = f"last {c.factor_sprints} closed sprints, {c.factor_from}"
    lines += [f"- Calibration factor: {c.factor:g} ({used}).", ""]
    return lines


def _next_status(repo: Path, number: int, status: str) -> str:
    """`planned` goes `current` only when that row comes right after this one in the table."""
    if status != "planned":
        return status
    _, at = _table((repo / "sprint" / "README.md").read_text().split("\n"))
    return "current" if at.get(str(number + 1)) == at[str(number)] + 1 else status


def _table(lines: list[str]) -> tuple[list[str], dict[str, int]]:
    """The `## Sprints` table's header and the line index of each row by its first cell."""
    start = next(i for i, x in enumerate(lines) if re.fullmatch(r"## Sprints\s*", x))
    rows = []
    for i in range(start + 1, len(lines)):
        if lines[i].startswith("## "):
            break
        if lines[i].lstrip().startswith("|"):
            rows.append(i)
        elif rows:
            break
    head = [c.lower() for c in _cells(lines[rows[0]])]
    return head, {_cells(lines[i])[0]: i for i in rows[2:]}


def _set_cell(line: str, column: int, value: str) -> str:
    parts = line.split("|")  # parts[0] is what comes before the row's first `|`
    parts[column + 1] = f" {value} "
    return "|".join(parts)


def _id_key(step_id: str) -> tuple[int, str]:
    digits = re.match(r"\d*", step_id)[0]  # type: ignore[index]
    return int(digits or 0), step_id
