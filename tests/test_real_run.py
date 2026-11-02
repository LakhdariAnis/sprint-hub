"""Step 506b: a run always gets out of `doing`, and its checklist ticks wherever it works."""

import asyncio
import subprocess
from pathlib import Path
from uuid import uuid4

from conftest import Recorder
from fastapi.testclient import TestClient

from hubd.api import create_app
from hubd.daemon import Hub
from hubd.model import State
from hubd.runners.claude import ClaudeCodeRunner
from hubd.runners.fake import FakeRunner
from hubd.vault import _load_step

STEP = Path("projects") / "demo" / "steps"
LATE = {"session_id": "3f2a…c91", "step": "102"}  # 102 is `doing` in the fixture


def test_finish_moves_a_doing_step_to_done(vault: Path, hub: Hub, notifier: Recorder) -> None:
    client = TestClient(create_app(hub))
    response = client.post("/steps/demo/102/finish")
    assert response.status_code == 200
    assert response.json()["state"] == "done"
    assert _load_step(vault / STEP / "102.md").state == State.done
    assert notifier.sent == []  # the key was pressed in the app: nothing to tell


def test_finish_only_from_doing_and_never_a_manual_step(vault: Path, hub: Hub) -> None:
    client = TestClient(create_app(hub))
    refused = client.post("/steps/demo/103/finish")  # 103 is `done`
    assert refused.status_code == 409
    assert refused.json() == {"detail": "step 103: no 'run_ended' from 'done'"}
    manual = vault / STEP / "101.md"
    manual.write_text(manual.read_text().replace("state: todo", "state: doing"))
    hub.entry("demo", "101").step.state = State.doing
    assert "manual step" in client.post("/steps/demo/101/finish").json()["detail"]
    assert client.post("/steps/demo/999/finish").status_code == 404


def test_second_finish_stops_at_done(hub: Hub) -> None:
    client = TestClient(create_app(hub))
    client.post("/steps/demo/102/finish")
    assert client.post("/steps/demo/102/finish").status_code == 409
    assert hub.entry("demo", "102").step.state == State.done


def test_late_hook_after_finish_changes_nothing(vault: Path, hub: Hub, notifier: Recorder) -> None:
    client = TestClient(create_app(hub))
    client.post("/steps/demo/102/finish")
    before = (vault / STEP / "102.md").read_bytes()
    late = client.post("/runs/ended", json=LATE)
    assert late.status_code == 200
    assert late.json()["state"] == "done"
    assert (vault / STEP / "102.md").read_bytes() == before
    assert notifier.sent == []


def test_second_hook_notifies_once(hub: Hub, notifier: Recorder) -> None:
    client = TestClient(create_app(hub))
    assert client.post("/runs/ended", json=LATE).status_code == 200
    assert client.post("/runs/ended", json=LATE).status_code == 200
    assert len(notifier.sent) == 1


class Gone(FakeRunner):
    """Every session has ended: Claude exited while hubd was down."""

    def running(self, session_id: str) -> bool:
        return False


def gone_hub(vault: Path, notifier: Recorder) -> Hub:
    return Hub(vault, lambda ended: Gone(ended, delay=0), notifier)


def test_hubd_down_flags_the_run_and_moves_nothing(vault: Path, notifier: Recorder) -> None:
    before = (vault / STEP / "102.md").read_bytes()
    client = TestClient(create_app(gone_hub(vault, notifier)))
    step = client.get("/steps/demo/102").json()
    assert (step["state"], step["run_gone"]) == ("doing", True)
    assert (vault / STEP / "102.md").read_bytes() == before
    assert client.get("/steps/demo/103").json()["run_gone"] is False  # `done`: not a stuck run
    assert client.post("/steps/demo/102/finish").json()["state"] == "done"


def test_live_session_is_not_flagged(hub: Hub) -> None:
    assert hub.entry("demo", "102").run_gone is False


def test_doing_without_a_run_is_flagged(vault: Path, notifier: Recorder) -> None:
    (vault / STEP / "150.md").write_text(
        "---\nstep: 150\ntitle: Imported\nstate: doing\nby: claude\n---\n"
    )
    assert gone_hub(vault, notifier).entry("demo", "150").run_gone is True


def test_flag_survives_a_reload_and_a_new_start_clears_it(vault: Path, notifier: Recorder) -> None:
    hub = gone_hub(vault, notifier)

    async def main() -> None:
        path = hub.entry("demo", "102").path
        path.write_text(path.read_text() + "\n")
        await hub.reload(path)
        assert hub.entry("demo", "102").run_gone is True
        hub._reload_all()
        assert hub.entry("demo", "102").run_gone is True

        await hub.finish("demo", "102")
        await hub.request_changes("demo", "102", "again")
        await hub.start("demo", "102")
        assert hub.entry("demo", "102").run_gone is False
        await asyncio.gather(*hub.runner.tasks.values())

    asyncio.run(main())


def test_claude_runner_finds_a_session_on_a_process_argv(tmp_path: Path) -> None:
    runner = ClaudeCodeRunner(["x"], "http://127.0.0.1:1", tmp_path / "settings.json")
    session = str(uuid4())
    assert runner.running(session) is False
    # `sh -c CMD NAME ARG`: the session stays on the argv while `sleep` runs.
    process = subprocess.Popen(["sh", "-c", "sleep 30; :", "claude", "--session-id", session])
    try:
        assert runner.running(session) is True
    finally:
        process.kill()
        process.wait()
    assert runner.running(session) is False
