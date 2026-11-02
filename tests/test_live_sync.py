"""Step 503: a new spec or project shows up without a restart."""

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path

import pytest
from conftest import Recorder
from fastapi.testclient import TestClient
from test_live import drain

from hubd import init
from hubd.api import create_app
from hubd.daemon import Hub
from hubd.runners.fake import FakeRunner

SPECS = Path("demo-repo") / "sprint"
STEP = Path("projects") / "demo" / "steps"


def test_new_spec_makes_a_step_and_an_event(vault: Path, hub: Hub) -> None:
    spec = hub.vault / SPECS / "199-live.md"
    spec.write_text("# Step 199 — Live test\n")

    async def main() -> list[dict]:
        with hub.subscribe() as queue:
            await hub.reload(spec)
            await hub.reload(spec)  # saved again: nothing new
            return drain(queue)

    [event] = asyncio.run(main())
    assert (event["type"], event["step"], event["title"], event["state"]) == (
        "step",
        "199",
        "Live test",
        "todo",
    )
    assert event["sprint"] == 1
    assert hub.entry("demo", "199").spec == spec
    assert (hub.vault / STEP / "199.md").is_file()


def test_existing_vault_step_is_left_alone(vault: Path, hub: Hub) -> None:
    step = hub.vault / STEP / "102.md"
    before = step.read_bytes()
    spec = hub.vault / SPECS / "102-api.md"
    spec.write_text(spec.read_text() + "edited\n")

    async def main() -> list[dict]:
        with hub.subscribe() as queue:
            await hub.reload(spec)
            return drain(queue)

    assert asyncio.run(main()) == []
    assert step.read_bytes() == before


def test_files_that_are_not_specs_import_nothing(vault: Path, hub: Hub) -> None:
    other = [hub.vault / SPECS / "README.md", hub.vault / SPECS / "PROGRESS.md"]
    for path in other:
        path.write_text("# Step 777 — Not a spec\n")

    async def main() -> list[dict]:
        with hub.subscribe() as queue:
            for path in other:
                await hub.reload(path)
            return drain(queue)

    assert asyncio.run(main()) == []
    assert len(hub.index.steps) == 5


def test_broken_new_spec_makes_no_step(
    vault: Path, hub: Hub, capsys: pytest.CaptureFixture[str]
) -> None:
    spec = hub.vault / SPECS / "198-bad.md"
    spec.write_text("no title line\n")
    asyncio.run(hub.reload(spec))
    assert not (hub.vault / STEP / "198.md").exists()
    assert "no '# Step <id> — <title>'" in capsys.readouterr().err


def test_deleted_spec_keeps_the_step_and_says_the_spec_is_gone(vault: Path, hub: Hub) -> None:
    spec = hub.vault / SPECS / "102-api.md"
    step = hub.vault / STEP / "102.md"
    assert hub.entry("demo", "102").spec == spec
    spec.unlink()

    async def main() -> list[dict]:
        with hub.subscribe() as queue:
            await hub.reload(spec)
            return drain(queue)

    [event] = asyncio.run(main())
    assert (event["type"], event["step"], event["spec"]) == ("step", "102", None)
    assert step.is_file()
    assert hub.entry("demo", "102").step.title == "Serve the API"


def test_spec_that_comes_back_for_a_kept_step(vault: Path, hub: Hub) -> None:
    spec = hub.vault / SPECS / "102-api.md"
    text = spec.read_text()
    spec.unlink()
    asyncio.run(hub.reload(spec))
    spec.write_text(text)

    async def main() -> list[dict]:
        with hub.subscribe() as queue:
            await hub.reload(spec)
            return drain(queue)

    [event] = asyncio.run(main())
    assert event["spec"] == text


async def until(check: Callable[[], bool], seconds: float = 8) -> None:
    for _ in range(int(seconds * 20)):
        if check():
            return
        await asyncio.sleep(0.05)
    raise AssertionError("not seen in time")


def config(path: Path, *projects: tuple[str, Path]) -> None:
    path.write_text("".join(f'[[project]]\nname = "{n}"\npath = "{p}"\n' for n, p in projects))


async def watching(hub: Hub, body: Callable[[], Awaitable[None]]) -> list[dict]:
    stop = asyncio.Event()
    task = asyncio.create_task(hub.watch(stop))
    await asyncio.sleep(0.3)  # let the watcher start
    with hub.subscribe() as queue:
        try:
            await body()
        finally:
            stop.set()
            await task
        return drain(queue)


def test_watch_picks_up_a_new_spec(vault: Path, hub: Hub) -> None:
    async def body() -> None:
        (hub.vault / SPECS / "199-live.md").write_text("# Step 199 — Live test\n")
        await until(lambda: any(e.step.step == "199" for e in hub.index.steps))

    events = asyncio.run(watching(hub, body))
    assert [e["step"] for e in events if e["type"] == "step"] == ["199"]


def test_new_project_in_projects_toml(vault: Path, notifier: Recorder, tmp_path: Path) -> None:
    repo = tmp_path / "elsewhere" / "hub-new"
    (repo / "sprint").mkdir(parents=True)
    (repo / "sprint" / "101-first.md").write_text("# Step 101 — First\n")
    toml = tmp_path / "cfg" / "projects.toml"
    toml.parent.mkdir()
    config(toml, ("demo", vault))
    hub = Hub(vault, lambda ended: FakeRunner(ended, delay=0), notifier, projects=toml)

    async def body() -> None:
        config(toml, ("demo", vault), ("hub new", repo))
        await until(lambda: "hub-new" in hub.index.projects)
        await until(lambda: any(e.project == "hub-new" for e in hub.index.steps))
        # Its sprint/ is watched now, no restart: a spec written later shows up.
        (repo / "sprint" / "102-second.md").write_text("# Step 102 — Second\n")
        await until(lambda: len([e for e in hub.index.steps if e.project == "hub-new"]) == 2)

    events = asyncio.run(watching(hub, body))
    assert {"type": "reload"} in events
    assert (vault / "projects" / "hub-new" / "project.md").is_file()
    assert hub.entry("hub-new", "101").step.title == "First"
    assert hub.index.projects["hub-new"].repo == repo
    # `demo` was in the file already: left as it was
    assert len([e for e in hub.index.steps if e.project == "demo"]) == 5


def test_project_removed_from_projects_toml_stays_in_the_vault(
    vault: Path, notifier: Recorder, tmp_path: Path
) -> None:
    toml = tmp_path / "cfg" / "projects.toml"
    toml.parent.mkdir()
    config(toml, ("demo", vault))
    hub = Hub(vault, lambda ended: FakeRunner(ended, delay=0), notifier, projects=toml)

    async def body() -> None:
        config(toml, ("demo", vault), ("other", vault))
        await until(lambda: "other" in hub.index.projects)
        config(toml, ("demo", vault))
        await asyncio.sleep(0.5)

    asyncio.run(watching(hub, body))
    assert "other" in hub.index.projects


def test_bad_projects_toml_is_an_error_not_a_crash(
    vault: Path, notifier: Recorder, tmp_path: Path
) -> None:
    toml = tmp_path / "cfg" / "projects.toml"
    toml.parent.mkdir()
    config(toml, ("demo", vault))
    hub = Hub(vault, lambda ended: FakeRunner(ended, delay=0), notifier, projects=toml)

    async def body() -> None:
        toml.write_text("[[project]\n")
        await until(lambda: any(e.path == hub.projects_file for e in hub.index.errors))

    events = asyncio.run(watching(hub, body))
    assert [e["type"] for e in events] == ["error"]


def test_repo_that_gets_sprint_later(vault: Path, notifier: Recorder, tmp_path: Path) -> None:
    repo = tmp_path / "late"
    repo.mkdir()
    folder = vault / "projects" / "late"
    (folder / "steps").mkdir(parents=True)
    (folder / "project.md").write_text(
        f"---\nname: late\nrepo: {repo}\nmodel: sonnet\nmerge: manual\n---\n"
    )
    hub = Hub(vault, lambda ended: FakeRunner(ended, delay=0), notifier)

    async def body() -> None:
        (repo / "sprint").mkdir()
        (repo / "sprint" / "101-first.md").write_text("# Step 101 — First\n")
        await until(lambda: any(e.project == "late" for e in hub.index.steps))
        # and it is watched from now on
        (repo / "sprint" / "102-second.md").write_text("# Step 102 — Second\n")
        await until(lambda: len([e for e in hub.index.steps if e.project == "late"]) == 2)

    asyncio.run(watching(hub, body))


def test_hubd_starts_without_a_vault_and_picks_it_up(tmp_path: Path, notifier: Recorder) -> None:
    vault = tmp_path / "Hub"
    repo = tmp_path / "repo"
    repo.mkdir()
    hub = Hub(vault, lambda ended: FakeRunner(ended, delay=0), notifier)
    client = TestClient(create_app(hub))
    assert (client.get("/projects").json(), client.get("/errors").json()) == ([], [])
    assert client.post("/steps/demo/101/start").status_code == 404

    async def body() -> None:
        (vault / "projects").mkdir(parents=True)
        init.create(vault / "projects" / "late", "late", repo)
        await until(lambda: "late" in hub.index.projects)

    events = asyncio.run(watching(hub, body))
    assert [e["type"] for e in events] == ["reload"]
    assert hub.index.steps == []  # init does not import
