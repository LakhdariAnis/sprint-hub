"""The `## Sprints` table of a project's `sprint/README.md`, the week view and the project ETA.

Files only: nothing here reads the clock, `today` always comes from the caller.
"""

import re
from dataclasses import dataclass
from datetime import date

from hubd.vault import StepEntry

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
        cells = _cells(line)
        if cells[0] in ("–", "—", "-"):  # `| – | … | parked |`: meant as no sprint, no warning
            continue
        try:
            sprints.append(_row(project, head, cells))
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


def week_of(day: date) -> str:
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


def sunday_of(week: str) -> date:
    year, number = map(int, week.split("-W"))
    return date.fromisocalendar(year, number, 7)


def step_hours(entry: StepEntry) -> float:
    """Agent time (a run with no end counts 0) plus Anis's own time, like the sprint bar."""
    return sum(r.minutes or 0 for r in entry.step.runs) / 60 + (entry.step.own_hours or 0)


def _progress(sprint: Sprint, steps: list[StepEntry]) -> tuple[int, int, float]:
    mine = [e for e in steps if e.project == sprint.project and e.step.sprint == sprint.number]
    done = sum(e.step.state == "approved" for e in mine)
    return done, len(mine), sum(step_hours(e) for e in mine)


def week_view(
    tables: dict[str, list[Sprint]], steps: list[StepEntry], names: dict[str, str], today: date
) -> dict:
    """This ISO week's sprints per track, with the flow D warnings."""
    week = week_of(today)
    sunday = sunday_of(week)
    tracks: dict[str, list[dict]] = {t: [] for t in TRACKS}
    for sprints in tables.values():
        for s in sprints:
            if s.week != week or s.track is None or s.status == "moved":
                continue
            done, total, hours = _progress(s, steps)
            tracks[s.track].append(
                {
                    "project": s.project,
                    "name": names.get(s.project, s.project),
                    "sprint": s.number,
                    "goal": s.goal,
                    "status": s.status,
                    "steps_done": done,
                    "steps_total": total,
                    "planned": s.planned,
                    "hours_done": round(s.actual if s.actual is not None else hours, 2),
                }
            )
    warnings = []
    for track, found in tracks.items():
        found.sort(key=lambda r: (r["name"], r["sprint"]))
        if len(found) > 1:
            who = ", ".join(f"{r['name']} {r['sprint']}" for r in found)
            warnings.append(f"{len(found)} {track} sprints in {week} ({who}). One per track.")
    if not tracks["work"]:
        warnings.append(f"No work sprint in {week}.")
    return {
        "week": week,
        "monday": date.fromisocalendar(*map(int, week.split("-W")), 1).isoformat(),
        "sunday": sunday.isoformat(),
        "days_left": (sunday - today).days + 1,  # today counts: Monday 7, Sunday 1
        "tracks": tracks,
        "warnings": warnings,
    }


def calibration(project: str, tables: dict[str, list[Sprint]]) -> tuple[float, int, str]:
    """(factor, sprints used, where from): actual ÷ planned of the last 3 closed sprints.

    The project's own; none of them recorded = the same track in all projects; else 1.0.
    """

    def last3(sprints: list[Sprint]) -> list[Sprint]:
        done = [s for s in sprints if s.status == "closed" and s.actual is not None and s.planned]
        return sorted(done, key=lambda s: (s.week or "", s.number))[-3:]

    mine = tables.get(project, [])
    used, source = last3(mine), "project"
    if not used:
        tracks = {s.track for s in mine if s.track}
        used = last3([s for t in tables.values() for s in t if s.track in tracks])
        source = "track"
    if not used:
        return 1.0, 0, "none"
    return sum(s.actual for s in used) / sum(s.planned for s in used), len(used), source  # type: ignore[misc]


def eta(project: str, tables: dict[str, list[Sprint]], steps: list[StepEntry], today: date) -> dict:
    """Flow C: open sprints, hours left times the factor, the week of the last one, and flags."""
    mine = tables.get(project, [])
    factor, used, source = calibration(project, tables)
    week = week_of(today)
    raw, flags, weeks = 0.0, [], []
    open_ = [s for s in mine if s.status in OPEN]
    for s in open_:
        done, total, _ = _progress(s, steps)
        # A sprint under way only counts the share of its steps that is not approved yet.
        raw += (s.planned or 0) * (1 - done / total if total else 1)
        if s.week is None:
            continue
        weeks.append(s.week)
        if s.week < week:
            flags.append(
                {
                    "sprint": s.number,
                    "kind": "overdue",
                    "text": f"Sprint {s.number} is overdue: its week was {s.week}.",
                }
            )
        elif s.status == "current" and s.week > week:
            flags.append(
                {
                    "sprint": s.number,
                    "kind": "wrong_week",
                    "text": f"Sprint {s.number} is current but planned for {s.week}.",
                }
            )
    finish = max([week, *weeks]) if open_ and weeks else None
    return {
        "data": bool(mine),
        "sprints": len(open_),
        "raw_hours": round(raw, 2),
        "hours": round(raw * factor, 2),
        "factor": round(factor, 2),
        "factor_sprints": used,
        "factor_from": source,
        "week": finish,
        "sunday": sunday_of(finish).isoformat() if finish else None,
        "flags": flags,
    }
