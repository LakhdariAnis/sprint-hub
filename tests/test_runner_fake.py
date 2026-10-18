import asyncio
import shutil
from pathlib import Path

import pytest

from hubd.model import Step
from hubd.runners import fake
from hubd.runners.fake import FakeRunner

REPO = Path(__file__).parent / "fixtures" / "vault" / "demo-repo"
STEP = Step(step="102", title="Serve the API", state="doing")


def test_ticks_in_order_then_run_ended_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shutil.copytree(REPO, tmp_path, dirs_exist_ok=True)
    progress = tmp_path / "sprint" / "progress" / "102.md"
    progress.unlink()
    seen: list[str] = []
    ended: list[tuple[str, str]] = []

    async def record(_: float) -> None:  # sleep runs after every write: snapshot it
        seen.append("".join(line[3] for line in progress.read_text().splitlines()[1:]))

    async def run_ended(session_id: str, step_id: str) -> None:
        ended.append((session_id, step_id))

    monkeypatch.setattr(fake, "sleep", record)

    async def main() -> None:
        runner = FakeRunner(run_ended, delay=0)
        await runner.start(STEP, "s1", "sonnet", tmp_path, "go")
        await runner.tasks["s1"]

    asyncio.run(main())
    assert seen == ["   ", "~  ", "x  ", "x~ ", "xx ", "xx~", "xxx"]
    assert ended == [("s1", "102")]
    assert progress.read_text() == (
        "# Step 102\n- [x] Add the FastAPI app\n- [x] Serve `/health`\n- [x] Test it\n"
    )


def test_resume_runs_the_same_step_again(tmp_path: Path) -> None:
    shutil.copytree(REPO, tmp_path, dirs_exist_ok=True)
    ended: list[tuple[str, str]] = []

    async def run_ended(session_id: str, step_id: str) -> None:
        ended.append((session_id, step_id))

    async def main() -> None:
        runner = FakeRunner(run_ended, delay=0)
        await runner.start(STEP, "s1", "sonnet", tmp_path, "go")
        await runner.tasks["s1"]
        await runner.resume(STEP, "s1", tmp_path, "fix it")
        await runner.tasks["s1"]

    asyncio.run(main())
    assert ended == [("s1", "102"), ("s1", "102")]


def test_missing_spec_raises(tmp_path: Path) -> None:
    async def run_ended(session_id: str, step_id: str) -> None:
        raise AssertionError("must not be called")

    async def main() -> None:
        runner = FakeRunner(run_ended, delay=0)
        await runner.start(STEP, "s1", "sonnet", tmp_path, "go")
        await runner.tasks["s1"]

    with pytest.raises(FileNotFoundError):
        asyncio.run(main())
