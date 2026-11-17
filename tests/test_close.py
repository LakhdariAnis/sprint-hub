import subprocess
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hubd import close
from hubd.api import create_app
from hubd.daemon import Hub
from hubd.states import InvalidTransition
from hubd.vault import _load_step

TODAY = date(2026, 11, 17)
HEAD = (
    "# Demo\n\nSome text | with a pipe.\n\n## Sprints\n\n"
    "| Sprint | Track | Week | Version | Goal | Planned | Actual | Status |\n"
    "|---|---|---|---|---|---|---|---|\n"
)
ROWS = (
    "| 1 | personal | 2026-W46 | 0.2.0 | Core  |  10 h | | current |\n"
    "| 2 | personal | 2026-W47 | 0.2.0 | Next | ~8 h | | planned |\n"
)
TAIL = "\nAfter the table.\n\n## Sprint 1 — steps\n\n| # | File |\n|---|---|\n| 101 | x |\n"
PROGRESS = (
    "# Progress\n\nDated log.\n\n"
    "## 2026-11-16 — Step 105 approved (branch step/105-x)\n\nTime: 1.5 h (agent 1 h)\n\n"
    "## 2026-11-15 — Step 101 built (branch step/101-x)\n\n- Built: things.\n\n"
    "## 2026-11-14 — Step 101 approved\n\nTime: 9 h (agent 9 h)\n\n"
    "## 2026-11-13 — Step 102 built\n\n- Built: no time here.\n"
)


@pytest.fixture
def repo(hub: Hub) -> Path:
    """demo-repo with a sprint table and a PROGRESS log; sprint 1 holds 101-105, 105 approved."""
    repo = hub.vault / "demo-repo"
    (repo / "sprint" / "README.md").write_text(HEAD + ROWS + TAIL)
    (repo / "sprint" / "PROGRESS.md").write_text(PROGRESS)
    return repo


def plan(hub: Hub, number: int = 1, own: float | None = None) -> close.Closed:
    tables, _ = hub.sprint_tables()
    return close.plan(hub.repo("demo"), "demo", number, own, hub.index.steps, tables)  # type: ignore[arg-type]


def test_step_times_take_the_newest_entry_of_each_step() -> None:
    assert close.step_times(PROGRESS) == {"105": 1.5, "101": 9.0}


def test_sums_without_own_hours(hub: Hub, repo: Path) -> None:
    c = plan(hub)
    assert c.hours == {"101": 9.0, "105": 1.5}
    assert c.no_time == ["102", "103", "104"]  # counted 0
    assert (c.actual, c.own_hours, c.planned) == (10.5, None, 10.0)
    assert c.moved == ["101", "102", "103", "104"]  # all but the approved 105
    assert (c.next, c.next_status) == (2, "current")
    assert (c.factor, c.factor_sprints, c.factor_from) == (1.05, 1, "project")


def test_own_hours_are_added(hub: Hub, repo: Path) -> None:
    c = plan(hub, own=2)
    assert (c.actual, c.own_hours) == (12.5, 2)
    assert c.factor == 1.25


def test_missing_next_row_refuses(hub: Hub, repo: Path) -> None:
    (repo / "sprint" / "README.md").write_text(HEAD + ROWS.split("\n")[0] + "\n")
    with pytest.raises(InvalidTransition, match="Sprint 2 has no row"):
        plan(hub)


def test_last_sprint_with_nothing_to_move_closes(hub: Hub, repo: Path) -> None:
    c = plan(hub, 2)  # sprint 2 has no step, so it needs no sprint 3 row
    assert (c.moved, c.next_status, c.actual) == ([], None, 0)


def test_a_closed_next_sprint_takes_no_steps(hub: Hub, repo: Path) -> None:
    (repo / "sprint" / "README.md").write_text(HEAD + ROWS.replace("| planned |", "| closed |"))
    with pytest.raises(InvalidTransition, match="Sprint 2 is closed"):
        plan(hub)


def test_closed_sprint_refuses(hub: Hub, repo: Path) -> None:
    (repo / "sprint" / "README.md").write_text(HEAD + ROWS.replace("| current |", "| closed |"))
    with pytest.raises(InvalidTransition, match="already closed"):
        plan(hub)


def test_unknown_sprint_refuses(hub: Hub, repo: Path) -> None:
    with pytest.raises(InvalidTransition, match="no Sprint 9 row"):
        plan(hub, 9)


def test_tracked_sprint_folder_refuses(hub: Hub, repo: Path) -> None:
    for args in (("init", "-q"), ("add", "sprint/README.md")):
        subprocess.run(["git", *args], cwd=repo, check=True)
    with pytest.raises(InvalidTransition, match="tracked by git"):
        plan(hub)


def test_plan_writes_nothing(hub: Hub, repo: Path) -> None:
    before = {p: p.read_bytes() for p in repo.rglob("*") if p.is_file()}
    plan(hub, own=2)
    assert {p: p.read_bytes() for p in repo.rglob("*") if p.is_file()} == before


def test_write_changes_only_the_cells(hub: Hub, repo: Path) -> None:
    close.write(repo, plan(hub, own=2), TODAY)
    text = (repo / "sprint" / "README.md").read_text()
    assert (
        text
        == HEAD
        + ROWS.replace("| | current |", "| 12.5 h | closed |").replace("| planned |", "| current |")
        + TAIL
    )


def test_next_row_not_right_after_stays_planned(hub: Hub, repo: Path) -> None:
    rows = ROWS.split("\n")
    other = "| 7 | work | 2026-W47 | 0.1.0 | Other | 3 h | | planned |"
    (repo / "sprint" / "README.md").write_text(HEAD + "\n".join([rows[0], other, rows[1]]) + "\n")
    c = plan(hub)
    assert c.next_status == "planned"
    close.write(repo, c, TODAY)
    assert "| Next | ~8 h | | planned |" in (repo / "sprint" / "README.md").read_text()


def test_progress_entry_on_top(hub: Hub, repo: Path) -> None:
    close.write(repo, plan(hub, own=2), TODAY)
    text = (repo / "sprint" / "PROGRESS.md").read_text()
    assert text == PROGRESS.replace(
        "## 2026-11-16",
        "## 2026-11-17 — Sprint 1 closed\n\n"
        "- Planned 10 h, actual 12.5 h (steps 10.5 h, Anis's own 2 h).\n"
        "- No `Time:` line, counted 0: 102, 103, 104.\n"
        "- Moved to Sprint 2: 101, 102, 103, 104.\n"
        "- Calibration factor: 1.25 (last 1 closed sprints, project).\n\n"
        "## 2026-11-16",
        1,
    )


def test_progress_file_missing_is_made(hub: Hub, repo: Path) -> None:
    (repo / "sprint" / "PROGRESS.md").unlink()
    c = plan(hub)
    assert (c.hours, c.actual) == ({}, 0)
    close.write(repo, c, TODAY)
    assert (
        (repo / "sprint" / "PROGRESS.md")
        .read_text()
        .startswith("# Progress\n\n## 2026-11-17 — Sprint 1 closed\n")
    )


def test_api_preview_writes_nothing(hub: Hub, repo: Path) -> None:
    files = [*repo.rglob("*"), *(hub.vault / "projects").rglob("*")]
    before = {p: p.read_bytes() for p in files if p.is_file()}
    client = TestClient(create_app(hub))
    for _ in range(2):
        r = client.get("/projects/demo/sprints/1/close", params={"own_hours": 2})
        assert r.status_code == 200
        assert (r.json()["actual"], r.json()["moved"]) == (12.5, ["101", "102", "103", "104"])
    assert {p: p.read_bytes() for p in files if p.is_file()} == before


def test_api_close_moves_the_steps(hub: Hub, repo: Path) -> None:
    client = TestClient(create_app(hub))
    r = client.post("/projects/demo/sprints/1/close", json={"own_hours": 2})
    assert (r.status_code, r.json()["actual"], r.json()["factor"]) == (200, 12.5, 1.25)
    steps = hub.vault / "projects" / "demo" / "steps"
    for step_id in ("101", "102", "103", "104"):
        assert _load_step(steps / f"{step_id}.md").sprint == 2
        assert "\nsprint: 2\n" in (steps / f"{step_id}.md").read_text()
    assert _load_step(steps / "105.md").sprint is None  # approved: stays, nothing written
    assert {e.step.step for e in hub.index.steps if e.step.sprint == 2} >= {"101", "104"}
    again = client.post("/projects/demo/sprints/1/close", json={"own_hours": 2})
    assert (again.status_code, again.json()["detail"]) == (409, "Sprint 1 is already closed")


def test_api_refusals(hub: Hub, repo: Path) -> None:
    client = TestClient(create_app(hub))
    assert client.post("/projects/nope/sprints/1/close").status_code == 404
    assert client.post("/projects/demo/sprints/1/close", json={"own_hours": -1}).status_code == 422
    (repo / "sprint" / "README.md").write_text(HEAD + ROWS.split("\n")[0] + "\n")
    r = client.post("/projects/demo/sprints/1/close")
    assert r.status_code == 409 and "Sprint 2 has no row" in r.json()["detail"]
