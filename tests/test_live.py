import asyncio
import time
from pathlib import Path

from fastapi.testclient import TestClient

from hubd.api import create_app
from hubd.daemon import Hub

STEPS = Path("projects") / "demo" / "steps"


def drain(queue: asyncio.Queue[dict]) -> list[dict]:
    events = []
    while not queue.empty():
        events.append(queue.get_nowait())
    return events


def test_step_edit_reloads_that_step(vault: Path, hub: Hub) -> None:
    path = hub.vault / STEPS / "101.md"

    async def main() -> list[dict]:
        with hub.subscribe() as queue:
            path.write_text(path.read_text().replace("state: todo", "state: doing"))
            await hub.reload(path)
            await hub.reload(path)  # same content again: no second event
            return drain(queue)

    [event] = asyncio.run(main())
    assert (event["type"], event["step"], event["state"]) == ("step", "101", "doing")
    assert hub.entry("demo", "101").step.state == "doing"
    assert len(hub.index.steps) == 5


def test_checklist_tick_emits_tasks(vault: Path, hub: Hub) -> None:
    path = hub.vault / "demo-repo" / "sprint" / "progress" / "102.md"

    async def main() -> list[dict]:
        with hub.subscribe() as queue:
            path.write_text(path.read_text().replace("[~]", "[x]"))
            await hub.reload(path)
            return drain(queue)

    [event] = asyncio.run(main())
    assert event["type"] == "tasks"
    assert [t["state"] for t in event["tasks"]] == ["done", "done", "todo"]
    # Only the task hubd saw change gets a time; the others changed before it watched.
    assert ["at" in t for t in event["tasks"]] == [False, True, False]


def test_tick_time_stays_when_other_tasks_change(vault: Path, hub: Hub) -> None:
    path = hub.vault / "demo-repo" / "sprint" / "progress" / "102.md"

    async def main() -> list[dict]:
        with hub.subscribe() as queue:
            path.write_text(path.read_text().replace("[~]", "[x]"))
            await hub.reload(path)
            path.write_text(path.read_text().replace("[ ]", "[~]"))
            await hub.reload(path)
            return drain(queue)

    first, second = asyncio.run(main())
    assert second["tasks"][1]["at"] == first["tasks"][1]["at"]
    assert "at" in second["tasks"][2]


def test_broken_edit_is_an_error_then_fixed(vault: Path, hub: Hub) -> None:
    path = hub.vault / STEPS / "103.md"
    good = path.read_text()

    async def main() -> list[dict]:
        with hub.subscribe() as queue:
            path.write_text(good.replace("state: done", "state: nope"))
            await hub.reload(path)
            assert [e.path for e in hub.index.errors if e.path == path] == [path]
            path.write_text(good)
            await hub.reload(path)
            return drain(queue)

    broken, fixed = asyncio.run(main())
    assert broken["type"] == "error" and broken["line"] == 4
    assert (fixed["type"], fixed["step"]) == ("step", "103")
    assert all(e.path != path for e in hub.index.errors)


def test_new_and_removed_step(vault: Path, hub: Hub) -> None:
    path = hub.vault / STEPS / "106.md"

    async def main() -> list[dict]:
        with hub.subscribe() as queue:
            path.write_text("---\nstep: 106\ntitle: New\nstate: todo\n---\n")
            await hub.reload(path)
            path.unlink()
            await hub.reload(path)
            return drain(queue)

    added, removed = asyncio.run(main())
    assert (added["type"], added["step"]) == ("step", "106")
    assert removed == {"type": "removed", "project": "demo", "step": "106"}
    assert len(hub.index.steps) == 5


def test_project_edit_reloads_all(vault: Path, hub: Hub) -> None:
    path = hub.vault / "projects" / "demo" / "project.md"

    async def main() -> list[dict]:
        with hub.subscribe() as queue:
            path.write_text(path.read_text().replace("model: sonnet", "model: opus"))
            await hub.reload(path)
            return drain(queue)

    assert asyncio.run(main()) == [{"type": "reload"}]
    assert hub.index.projects["demo"].model == "opus"


def test_file_edit_shows_in_get_within_1s(vault: Path, hub: Hub) -> None:
    path = hub.vault / STEPS / "101.md"
    edited = path.read_text().replace("state: todo", "state: doing")
    with TestClient(create_app(hub)) as client:
        time.sleep(0.2)  # let the watcher start
        path.write_text(edited)
        written = time.monotonic()
        while client.get("/steps/demo/101").json()["state"] != "doing":
            assert time.monotonic() - written < 1, "edit not seen within 1 s"
            time.sleep(0.02)


def test_deadlines_edit_reloads_them(vault: Path, hub: Hub) -> None:
    path = hub.vault / "deadlines.md"

    async def main() -> list[dict]:
        with hub.subscribe() as queue:
            path.write_text("- 2026-11-03 Apply #internship\n- someday Oops\n")
            await hub.reload(path)
            return drain(queue)

    assert [e["type"] for e in asyncio.run(main())] == ["reload"]
    assert [d.text for d in hub.index.deadlines] == ["Apply"]
    assert [e.line for e in hub.index.errors if e.path == path] == [2]
    path.unlink()
    asyncio.run(hub.reload(path))
    assert hub.index.deadlines == []
    assert not [e for e in hub.index.errors if e.path == path]
