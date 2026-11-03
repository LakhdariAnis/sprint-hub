"""Step 513c: planned hours, agent time, the `Time:` line in PROGRESS."""

import asyncio
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from conftest import Recorder
from fastapi.testclient import TestClient
from test_approve import git
from test_live import drain
from test_live_sync import until, watching

from hubd.api import create_app
from hubd.daemon import Hub, step_json
from hubd.model import Run, State, Step
from hubd.vault import _load_step, format_run, planned_hours, save_step, save_time, time_line

COMMANDS = Path("demo-repo/.claude/commands")


def command(vault: Path, step_id: str, head: str) -> Path:
    path = vault / COMMANDS / f"sprint-{step_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\ndescription: Sprint {step_id} - a: b\n{head}\n---\nDo it.\n")
    return path


@pytest.mark.parametrize(
    ("head", "planned"),
    [
        ("hours: 1", 1.0),
        ("hours: 0.5", 0.5),
        ("hours: 0", 0.0),
        ("model: haiku", None),
        ("hours: soon", None),
        ("hours: -1", None),
        ("hours: inf", None),
    ],
)
def test_planned_hours(vault: Path, head: str, planned: float | None) -> None:
    command(vault, "102", head)
    assert planned_hours(vault / "demo-repo", "102") == planned


def test_no_command_file_means_no_planned_hours(vault: Path) -> None:
    assert planned_hours(vault / "demo-repo", "102") is None


def test_archived_command_counts(vault: Path) -> None:
    path = vault / "demo-repo/sprint/archive/sprint-1/commands/sprint-102.md"
    path.parent.mkdir(parents=True)
    path.write_text("---\nhours: 2\n---\n")
    assert planned_hours(vault / "demo-repo", "102") == 2.0


def test_step_json_has_planned(vault: Path, hub: Hub) -> None:
    assert step_json(hub.entry("demo", "102"))["planned"] is None


def test_changed_command_updates_the_step_live(vault: Path, hub: Hub) -> None:
    path = command(vault, "102", "hours: 1")

    async def main() -> list[dict]:
        with hub.subscribe() as queue:
            await hub.reload(path.resolve())
            await hub.reload(path.resolve())  # saved again: nothing new
            path.write_text("---\nhours: 2\n---\n")
            await hub.reload(path.resolve())
            path.unlink()
            await hub.reload(path.resolve())
            return drain(queue)

    events = asyncio.run(main())
    assert [(e["type"], e["step"], e["planned"]) for e in events] == [
        ("step", "102", 1.0),
        ("step", "102", 2.0),
        ("step", "102", None),
    ]


def test_watcher_sees_a_command_file(vault: Path, hub: Hub) -> None:
    path = command(vault, "102", "hours: 1")

    async def body() -> None:
        path.write_text("---\nhours: 3\n---\n")
        await until(lambda: hub.entry("demo", "102").planned == 3.0)

    asyncio.run(watching(hub, body))


def started(hub: Hub, step_id: str, minutes_ago: int) -> Run:
    """The latest run of the step, moved back in time, in the file and the index."""
    entry = hub.entry("demo", step_id)
    run = entry.step.runs[-1]
    when = datetime.now().replace(second=0, microsecond=0) - timedelta(minutes=minutes_ago)
    text = entry.path.read_text()
    entry.path.write_text(text.replace(f"{run.started:%Y-%m-%d %H:%M}", f"{when:%Y-%m-%d %H:%M}"))
    entry.step = _load_step(entry.path)
    return entry.step.runs[-1]


def test_run_ended_writes_the_minutes_in_the_run_line(vault: Path, hub: Hub) -> None:
    run = started(hub, "102", 42)  # 102 is `doing` in the fixture
    asyncio.run(hub.run_ended(run.session, "102"))
    entry = hub.entry("demo", "102")
    minutes = entry.step.runs[-1].minutes
    assert minutes in (42, 43)  # 43 if the clock passed a minute during the test
    assert _load_step(entry.path).runs[-1].minutes == minutes
    assert f"{format_run(entry.step.runs[-1])}\n" in entry.path.read_text()
    assert f" · {minutes} min · " in entry.path.read_text()


def test_only_the_run_line_changes(vault: Path, hub: Hub) -> None:
    entry = hub.entry("demo", "102")
    run = started(hub, "102", 5)
    before = entry.path.read_text().splitlines()
    asyncio.run(hub.run_ended(run.session, "102"))
    after = entry.path.read_text().splitlines()
    changed = [(a, b) for a, b in zip(before, after, strict=True) if a != b]
    assert len(changed) == 2
    assert changed[0][0].startswith("state: doing") and changed[0][1].startswith("state: done")
    minutes = entry.step.runs[-1].minutes
    assert changed[1][1] == changed[1][0].replace(" · task", f" · {minutes} min · task")


def test_other_changes_to_a_run_line_are_refused(vault: Path, hub: Hub) -> None:
    entry = hub.entry("demo", "102")
    new = entry.step.model_copy(deep=True)
    new.runs[-1].model = "opus"
    with pytest.raises(ValueError, match="only be appended"):
        save_step(entry.path, new)


def test_finish_on_a_live_session_records_the_end(vault: Path, hub: Hub) -> None:
    started(hub, "102", 30)
    asyncio.run(hub.finish("demo", "102"))  # FakeRunner says every session is alive
    assert hub.entry("demo", "102").step.runs[-1].minutes in (30, 31)


def test_finish_on_a_gone_session_leaves_no_end(
    vault: Path, hub: Hub, monkeypatch: pytest.MonkeyPatch
) -> None:
    started(hub, "102", 3000)
    monkeypatch.setattr(hub.runner, "running", lambda _: False)
    asyncio.run(hub.finish("demo", "102"))
    entry = hub.entry("demo", "102")
    assert entry.step.state == State.done
    assert entry.step.runs[-1].minutes is None
    assert _load_step(entry.path).runs[-1].minutes is None


def time_step(**fields: object) -> Step:
    runs = [
        Run(started="2026-11-02 10:00", model="haiku", session="s", minutes=m) for m in (30, 15)
    ]
    return Step(step="901", title="T", state="approved", runs=runs, **fields)


@pytest.mark.parametrize(
    ("own", "line"),
    [
        (None, "Time: 0.75 h (agent 0.75 h, Anis not recorded)"),
        (0, "Time: 0.75 h (agent 0.75 h)"),
        (0.5, "Time: 1.25 h (agent 0.75 h)"),
    ],
)
def test_time_line(own: float | None, line: str) -> None:
    assert time_line(time_step(own_hours=own)) == line


def test_a_run_with_no_end_counts_zero() -> None:
    step = time_step()
    step.runs.append(Run(started="2026-11-02 12:00", model="haiku", session="t"))
    assert time_line(step) == "Time: 0.75 h (agent 0.75 h, Anis not recorded)"


PROGRESS = """# Progress

Log.


## 2026-11-02 — Step 902 built (branch step/902-x)

- Built: it.

## 2026-11-01 — Step 901 built (branch step/901-x)

- Built: that.

## 2026-10-30 — Step 901 reviewed (branch step/901-x)
Merged into `v2`.
"""


def test_time_goes_in_the_newest_entry_of_the_step_and_nothing_else_moves(tmp_path: Path) -> None:
    path = tmp_path / "PROGRESS.md"
    path.write_text(PROGRESS)
    save_time(path, time_step(own_hours=0.5), None, date(2026, 11, 2))
    assert path.read_text() == PROGRESS.replace(
        "Step 901 built (branch step/901-x)\n",
        "Step 901 built (branch step/901-x)\n\nTime: 1.25 h (agent 0.75 h)\n",
    )


def test_entry_with_text_right_under_the_heading_keeps_its_text(tmp_path: Path) -> None:
    path = tmp_path / "PROGRESS.md"
    path.write_text(PROGRESS)
    save_time(path, time_step(), None, date(2026, 11, 2))
    step = time_step()
    step.step = "901x"  # no such entry: 901 must not match 901x, nor the reverse
    save_time(path, step, None, date(2026, 11, 2))
    assert path.read_text().count("— Step 901 built") == 1
    assert "## 2026-11-02 — Step 901x approved\n" in path.read_text()


def test_time_line_is_replaced_not_added_twice(tmp_path: Path) -> None:
    path = tmp_path / "PROGRESS.md"
    path.write_text(PROGRESS)
    save_time(path, time_step(), None, date(2026, 11, 2))
    save_time(path, time_step(own_hours=1), None, date(2026, 11, 2))
    assert path.read_text().count("Time: ") == 1
    assert "Time: 1.75 h (agent 0.75 h)\n" in path.read_text()


def test_no_entry_adds_one_on_top_in_the_file_format(tmp_path: Path) -> None:
    path = tmp_path / "PROGRESS.md"
    path.write_text(PROGRESS.replace("Step 901", "Step 800"))
    original = path.read_text()
    save_time(
        path, time_step(branch="step/901-x"), "Merged into `main` in `abc1234`.", date(2026, 11, 2)
    )
    entry = (
        "## 2026-11-02 — Step 901 approved (branch step/901-x)\n\n"
        "Merged into `main` in `abc1234`.\n\n"
        "Time: 0.75 h (agent 0.75 h, Anis not recorded)\n\n"
    )
    assert path.read_text() == original.replace(
        "## 2026-11-02 — Step 902", entry + "## 2026-11-02 — Step 902"
    )


@pytest.mark.parametrize("start", [None, "", "# Progress\n"])
def test_file_with_no_entry_gets_one(tmp_path: Path, start: str | None) -> None:
    path = tmp_path / "PROGRESS.md"
    if start is not None:
        path.write_text(start)
    save_time(path, time_step(), None, date(2026, 11, 2))
    assert path.read_text() == (
        "# Progress\n\n## 2026-11-02 — Step 901 approved\n\n"
        "Time: 0.75 h (agent 0.75 h, Anis not recorded)\n"
    )


@pytest.fixture
def merged_repo(vault: Path) -> Path:
    """demo-repo on main, with branch step/103-ui; `sprint/` ignored like the real projects."""
    repo = vault / "demo-repo"
    for args in (
        ("init", "-q", "-b", "main"),
        ("config", "user.name", "test"),
        ("config", "user.email", "test@hubd.invalid"),
    ):
        git(repo, *args)
    (repo / ".gitignore").write_text("sprint/\n")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "start")
    git(repo, "checkout", "-q", "-b", "step/103-ui")
    (repo / "ui.txt").write_text("ui\n")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "ui")
    git(repo, "checkout", "-q", "main")
    return repo


def test_approve_with_hours_writes_step_and_progress(
    vault: Path, hub: Hub, merged_repo: Path
) -> None:
    client = TestClient(create_app(hub))
    reply = client.post("/steps/demo/103/approve", json={"own_hours": 0.5})
    assert reply.status_code == 200
    assert reply.json()["own_hours"] == 0.5
    entry = hub.entry("demo", "103")
    assert _load_step(entry.path).own_hours == 0.5
    text = (merged_repo / "sprint/PROGRESS.md").read_text()
    assert "Time: 1.2 h (agent 0.7 h)\n" in text  # 103 has a 42 min run
    assert f"Merged into `main` in `{git(merged_repo, 'rev-parse', '--short', 'HEAD')}`." in text
    assert git(merged_repo, "status", "--short") == ""


@pytest.mark.parametrize("body", [None, {}, {"own_hours": None}])
def test_approve_with_empty_field_is_not_recorded(
    vault: Path, hub: Hub, merged_repo: Path, body: dict | None
) -> None:
    client = TestClient(create_app(hub))
    reply = client.post("/steps/demo/103/approve", json=body)
    assert reply.status_code == 200
    assert reply.json()["own_hours"] is None
    assert "own_hours" not in hub.entry("demo", "103").path.read_text()
    assert "Anis not recorded" in (merged_repo / "sprint/PROGRESS.md").read_text()


@pytest.mark.parametrize("hours", [-1, "soon"])
def test_api_refuses_bad_hours_before_any_merge(hub: Hub, merged_repo: Path, hours: object) -> None:
    client = TestClient(create_app(hub))
    assert client.post("/steps/demo/103/approve", json={"own_hours": hours}).status_code == 422
    assert hub.entry("demo", "103").step.state == State.done


def test_tracked_progress_is_left_alone_and_warned(
    vault: Path, hub: Hub, merged_repo: Path, notifier: Recorder
) -> None:
    (merged_repo / ".gitignore").unlink()
    progress = merged_repo / "sprint/PROGRESS.md"
    progress.write_text(PROGRESS)
    git(merged_repo, "add", ".")
    git(merged_repo, "commit", "-q", "-m", "track sprint")
    asyncio.run(hub.approve("demo", "103"))
    assert progress.read_text() == PROGRESS
    assert git(merged_repo, "status", "--short") == ""
    assert hub.entry("demo", "103").step.state == State.approved
    assert notifier.sent[-1][0] == "Time not written"


def test_failed_write_never_undoes_the_approve(
    vault: Path, hub: Hub, merged_repo: Path, notifier: Recorder
) -> None:
    (merged_repo / "sprint/PROGRESS.md").mkdir()
    asyncio.run(hub.approve("demo", "103"))
    assert hub.entry("demo", "103").step.state == State.approved
    assert notifier.sent[-1][0] == "Time not written"


def test_repo_with_no_sprint_folder_gets_none(vault: Path, hub: Hub, merged_repo: Path) -> None:
    shutil.rmtree(merged_repo / "sprint")
    asyncio.run(hub.approve("demo", "103"))
    assert hub.entry("demo", "103").step.state == State.approved
    assert not (merged_repo / "sprint").exists()
