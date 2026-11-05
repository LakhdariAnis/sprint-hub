"""The `## Sprints` table of a project's `sprint/README.md`, the week view and the project ETA.

Files only: nothing here reads the clock, `today` always comes from the caller.
"""

import re
from dataclasses import dataclass
from datetime import date

TRACKS = ("work", "personal")
OPEN = ("planned", "current")
STATUSES = (*OPEN, "closed", "moved")
_WEEK = re.compile(r"(\d{4})-W(\d{2})")
_HOURS = re.compile(r"~?(\d+(?:\.\d+)?) h")
_REQUIRED = ("sprint", "track", "week", "planned", "status")


@dataclass
class Sprint:
    project: str
    number: int
    track: str | None  # None: not scheduled yet
    week: str | None  # `2026-W45`; None: not scheduled yet
    goal: str
    planned: float | None
    actual: float | None  # None: empty or "not recorded"
    status: str


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def parse_sprints(project: str, text: str) -> tuple[list[Sprint], list[tuple[int | None, str]]]:
    """Rows of the first table under `## Sprints`, and (line, message) for each thing skipped."""
    lines = text.splitlines()
    start = next((i for i, x in enumerate(lines) if re.fullmatch(r"## Sprints\s*", x)), None)
    table = []  # (line number, text)
    for i in range(start + 1 if start is not None else len(lines), len(lines)):
        if lines[i].startswith("## "):
            break
        if lines[i].lstrip().startswith("|"):
            table.append((i + 1, lines[i]))
        elif table:
            break
    if len(table) < 2:
        return [], [
            (start + 1 if start is not None else None, "no sprint table under `## Sprints`")
        ]
    head = [c.lower() for c in _cells(table[0][1])]
    if missing := [c for c in _REQUIRED if c not in head]:
        return [], [(table[0][0], f"sprint table lacks column {', '.join(missing)}")]
    sprints, warnings = [], []
    for n, line in table[2:]:  # table[1] is the `|---|` line
        try:
            sprints.append(_row(project, head, _cells(line)))
        except ValueError as exc:
            warnings.append((n, f"sprint row skipped: {exc}"))
    return sprints, warnings


def _row(project: str, head: list[str], cells: list[str]) -> Sprint:
    if len(cells) != len(head):
        raise ValueError(f"{len(cells)} cells, the header has {len(head)}")
    row = dict(zip(head, cells, strict=True))
    if not row["sprint"].isdecimal():
        raise ValueError(f"sprint {row['sprint']!r} is not a number")
    track, week = row["track"] or None, row["week"] or None
    if track is not None and track not in TRACKS:
        raise ValueError(f"track {track!r} is not work or personal")
    if week is not None and not _valid_week(week):
        raise ValueError(f"week {week!r} is not like 2026-W45")
    if row["status"] not in STATUSES:
        raise ValueError(f"status {row['status']!r} is not one of {', '.join(STATUSES)}")
    planned = None
    if row["planned"]:
        if not (m := _HOURS.fullmatch(row["planned"])):
            raise ValueError(f"planned {row['planned']!r} is not like 14 h")
        planned = float(m[1])
    m = _HOURS.fullmatch(row.get("actual", ""))
    return Sprint(
        project=project,
        number=int(row["sprint"]),
        track=track,
        week=week,
        goal=row.get("goal", ""),
        planned=planned,
        actual=float(m[1]) if m else None,
        status=row["status"],
    )


def _valid_week(week: str) -> bool:
    m = _WEEK.fullmatch(week)
    try:
        return bool(m) and bool(date.fromisocalendar(int(m[1]), int(m[2]), 1))
    except ValueError:
        return False
