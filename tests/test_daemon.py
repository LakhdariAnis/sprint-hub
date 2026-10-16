import asyncio
import shutil
from pathlib import Path

import pytest

from hubd.daemon import Hub, NotFound
from hubd.model import State
from hubd.runners.fake import FakeRunner
from hubd.states import InvalidTransition
from hubd.vault import _load_step

FIXTURE = Path(__file__).parent / "fixtures" / "vault"


class Recorder:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def notify(self, title: str, body: str) -> None:
        self.sent.append((title, body))


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    shutil.copytree(FIXTURE, tmp_path, dirs_exist_ok=True)
    (tmp_path / "demo-repo" / "sprint" / "104-retry.md").write_text(
        "# Step 104 — Retry\n\n## Tasks\n- Find the bug\n- Fix it\n"
    )
    return tmp_path


def make_hub(vault: Path, notifier: Recorder | None = None) -> Hub:
    return Hub(vault, lambda ended: FakeRunner(ended, delay=0), notifier or Recorder())


def test_start_ticks_then_done_saved(vault: Path) -> None:
    notifier = Recorder()
    step_file = vault / "projects" / "demo" / "steps" / "104.md"

    async def main() -> None:
        hub = make_hub(vault, notifier)
        step = await hub.start("demo", "104")  # 104 is in `changes`
        assert step.state == State.doing
        saved = _load_step(step_file)
        assert saved.state == State.doing
        session = saved.runs[-1].session
        assert (saved.runs[-1].model, session) == ("sonnet", step.runs[-1].session)
        await hub.runner.tasks[session]
        assert hub.entry("demo", "104").step.state == State.done

    asyncio.run(main())
    assert _load_step(step_file).state == State.done
    progress = vault / "demo-repo" / "sprint" / "progress" / "104.md"
    assert progress.read_text() == "# Step 104\n- [x] Find the bug\n- [x] Fix it\n"
    assert notifier.sent == [("Run ended", "demo 104 Write the docs: review it")]


def test_invalid_starts(vault: Path) -> None:
    async def main() -> None:
        hub = make_hub(vault)
        with pytest.raises(InvalidTransition, match="no 'start' from 'done'"):
            await hub.start("demo", "103")
        with pytest.raises(InvalidTransition, match="by: me"):
            await hub.start("demo", "101")
        with pytest.raises(NotFound):
            await hub.start("demo", "999")

    asyncio.run(main())


def test_run_ended_checks_the_session(vault: Path) -> None:
    async def main() -> None:
        hub = make_hub(vault)
        with pytest.raises(NotFound):
            await hub.run_ended("unknown", "102")
        with pytest.raises(NotFound):
            await hub.run_ended("3f2a…c91", "103")  # session of 102, wrong step
        done = await hub.run_ended("3f2a…c91", "102")  # 102 is `doing` in the fixture
        assert done.state == State.done

    asyncio.run(main())


def test_runner_failure_restores_the_file(vault: Path) -> None:
    step_file = vault / "projects" / "demo" / "steps" / "104.md"
    before = step_file.read_bytes()

    class Broken(FakeRunner):
        async def start(self, *args: object) -> None:
            raise OSError("no terminal")

    async def main() -> None:
        hub = Hub(vault, lambda ended: Broken(ended), Recorder())
        with pytest.raises(OSError):
            await hub.start("demo", "104")
        assert hub.entry("demo", "104").step.state == State.changes

    asyncio.run(main())
    assert step_file.read_bytes() == before
