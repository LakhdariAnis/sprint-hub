"""Step 513c: planned hours, agent time, the `Time:` line in PROGRESS."""

import asyncio
from pathlib import Path

import pytest
from test_live import drain
from test_live_sync import until, watching

from hubd.daemon import Hub, step_json
from hubd.vault import planned_hours

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
