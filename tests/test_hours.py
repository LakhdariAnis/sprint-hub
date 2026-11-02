"""Step 513c: planned hours, agent time, the `Time:` line in PROGRESS."""

import asyncio
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from test_live import drain
from test_live_sync import until, watching

from hubd.daemon import Hub, step_json
from hubd.model import Run, State
from hubd.vault import _load_step, format_run, planned_hours, save_step

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
