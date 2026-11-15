import asyncio
from pathlib import Path

import pytest
from conftest import Recorder

from hubd.daemon import Hub, NotFound
from hubd.model import State
from hubd.runners.fake import FakeRunner
from hubd.states import InvalidTransition
from hubd.vault import _load_step

SESSION = "7b1e…a04"  # 103's run, `done` in the fixture


@pytest.fixture
def closed(vault: Path, hub: Hub) -> Hub:
    """The fixture hub with 103's terminal closed: its session is gone, its spec is there."""
    (vault / "demo-repo" / "sprint" / "103-ui.md").write_text("# Step 103\n\n## Tasks\n- Show it\n")
    hub.runner.ended.add(SESSION)
    return hub


def test_reopen_from_done_resumes_the_last_chat(
    vault: Path, closed: Hub, notifier: Recorder
) -> None:
    async def main() -> None:
        step = await closed.reopen("demo", "103")
        assert step.state == State.doing
        saved = _load_step(vault / "projects" / "demo" / "steps" / "103.md")
        assert saved.state == State.doing
        assert [(r.session, r.model, r.minutes) for r in saved.runs] == [
            (SESSION, "sonnet", 42),
            (SESSION, "sonnet", None),
        ]
        assert closed.runner.resumed == [(SESSION, "")]
        await closed.runner.tasks[SESSION]  # the fake run ends: the hook matches the new line

    asyncio.run(main())
    step = _load_step(vault / "projects" / "demo" / "steps" / "103.md")
    assert step.state == State.done
    assert [r.minutes for r in step.runs] == [42, 0]
    assert notifier.sent == [
        ("Run ended", "demo 103 Show the list: review it, or o reopens the chat")
    ]


def test_reopen_a_gone_doing_run_stays_doing(vault: Path, hub: Hub) -> None:
    entry = hub.entry("demo", "102")
    entry.run_gone = True
    hub.runner.ended.add("3f2a…c91")
    step = asyncio.run(hub.reopen("demo", "102"))
    assert step.state == State.doing
    assert [r.session for r in step.runs] == ["3f2a…c91", "3f2a…c91"]
    assert entry.run_gone is False
    assert len(_load_step(entry.path).runs) == 2


def test_reopen_refusals(closed: Hub, monkeypatch: pytest.MonkeyPatch) -> None:
    def refused(step_id: str, match: str) -> None:
        with pytest.raises(InvalidTransition, match=match):
            asyncio.run(closed.reopen("demo", step_id))

    refused("101", "manual step")
    refused("102", "the chat is still open")  # FakeRunner: a session it did not end is alive
    closed.runner.ended.update({"3f2a…c91", "9c3d…e12", "1a2b…f00"})
    refused("102", "no 'reopen' from 'doing'")  # gone, but hubd has not flagged it
    refused("104", "no 'reopen' from 'changes'")
    refused("105", "no 'reopen' from 'approved'")
    with pytest.raises(NotFound):
        asyncio.run(closed.reopen("demo", "999"))

    asked: list[tuple[bool, str | None]] = []

    def refusal(step_id: str, cwd: Path, fresh: bool, running: str | None) -> str | None:
        asked.append((fresh, running))
        return running and f"step {running} is running in this repo, wait for it to end"

    monkeypatch.setattr(closed.runner, "refusal", refusal)
    refused("103", "step 102 is running in this repo")
    assert asked == [(False, "102")]

    entry = closed.entry("demo", "103")
    entry.step = entry.step.model_copy(update={"runs": []})
    refused("103", "no run yet")
    assert closed.runner.resumed == []


def test_runner_failure_restores_the_file(vault: Path) -> None:
    step_file = vault / "projects" / "demo" / "steps" / "102.md"
    before = step_file.read_bytes()

    class Broken(FakeRunner):
        def running(self, session_id: str) -> bool:
            return False

        async def resume(self, *args: object) -> None:
            raise OSError("no terminal")

    async def main() -> None:
        hub = Hub(vault, lambda ended: Broken(ended), Recorder())
        assert hub.entry("demo", "102").run_gone
        with pytest.raises(OSError):
            await hub.reopen("demo", "102")
        entry = hub.entry("demo", "102")
        assert (entry.step.state, len(entry.step.runs), entry.run_gone) == (State.doing, 1, True)
        with pytest.raises(OSError):
            await hub.reopen("demo", "103")
        assert hub.entry("demo", "103").step.state == State.done

    asyncio.run(main())
    assert step_file.read_bytes() == before
    assert len(_load_step(vault / "projects" / "demo" / "steps" / "103.md").runs) == 1
