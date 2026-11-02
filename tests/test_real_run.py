"""Step 506b: a run always gets out of `doing`, and its checklist ticks wherever it works."""

import asyncio
import os
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest
from conftest import Recorder
from fastapi.testclient import TestClient
from test_live import drain
from test_live_sync import until, watching

from hubd.api import create_app
from hubd.daemon import Hub
from hubd.model import State, TaskState
from hubd.runners.claude import ClaudeCodeRunner
from hubd.runners.fake import FakeRunner
from hubd.vault import _load_step, live_file, worktrees

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


@pytest.fixture
def repo(vault: Path) -> Path:
    """The demo repo as a git repo, as `git worktree add` needs one."""
    cwd = vault / "demo-repo"
    git(cwd, "init", "-q", "-b", "main")
    name = ("-c", "user.name=t", "-c", "user.email=t@t")
    git(cwd, *name, "commit", "-q", "--allow-empty", "-m", "t")
    return cwd


def git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def add_worktree(repo: Path, name: str) -> Path:
    tree = repo.parent / name
    git(repo, "worktree", "add", "-q", str(tree), "-b", name)
    return tree


def write(tree: Path, folder: str, step: str, text: str, age: float = 0) -> Path:
    path = tree / "sprint" / folder / f"{step}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    when = time.time() - age
    os.utime(path, (when, when))
    return path


def texts(hub: Hub, step: str) -> list[str]:
    return [t.text for t in hub.entry("demo", step).tasks]


def test_worktrees_lists_what_git_lists(repo: Path) -> None:
    assert worktrees(repo) == []
    tree = add_worktree(repo, "wt")
    listed = subprocess.run(
        ["git", "worktree", "list", "--porcelain"], cwd=repo, capture_output=True, text=True
    ).stdout
    assert f"worktree {tree}\n" in listed
    assert worktrees(repo) == [tree]
    shutil.rmtree(tree)  # removed by hand: git still lists it, there is nothing to read
    assert worktrees(repo) == []


def test_worktrees_of_a_folder_that_is_no_repo(tmp_path: Path) -> None:
    assert worktrees(tmp_path / "nothing") == []


def test_worktree_progress_and_questions_load_at_start(repo: Path, notifier: Recorder) -> None:
    tree = add_worktree(repo, "wt")
    write(tree, "progress", "103", "# Step 103\n- [x] from worktree\n")
    write(tree, "questions", "103", "# Step 103\n- [ ] from worktree?\n")
    hub = Hub(repo.parent, lambda ended: FakeRunner(ended, delay=0), notifier)
    assert texts(hub, "103") == ["from worktree"]
    assert hub.entry("demo", "103").questions[0].text == "from worktree?"


def test_newest_file_wins(repo: Path, notifier: Recorder) -> None:
    tree = add_worktree(repo, "wt")
    write(repo, "progress", "103", "- [ ] main\n", age=100)
    write(tree, "progress", "103", "- [ ] worktree\n", age=50)
    assert live_file(repo, "progress", "103") == tree / "sprint" / "progress" / "103.md"
    write(repo, "progress", "103", "- [ ] main\n")
    assert live_file(repo, "progress", "103") == repo / "sprint" / "progress" / "103.md"


def test_worktree_tick_emits_tasks_and_an_older_file_loses(repo: Path, notifier: Recorder) -> None:
    tree = add_worktree(repo, "wt")
    hub = Hub(repo.parent, lambda ended: FakeRunner(ended, delay=0), notifier)
    older = write(repo, "progress", "103", "- [ ] main\n", age=100)
    path = write(tree, "progress", "103", "- [x] worktree\n")

    async def main() -> list[dict]:
        with hub.subscribe() as queue:
            await hub.reload(path)
            await hub.reload(older)  # the older file changed on disk: it is still the older one
            return drain(queue)

    [event] = asyncio.run(main())
    assert (event["type"], event["tasks"][0]["text"]) == ("tasks", "worktree")


def test_worktree_added_during_a_run(repo: Path, notifier: Recorder) -> None:
    hub = Hub(repo.parent, lambda ended: FakeRunner(ended, delay=0), notifier)
    ticked = {"Build the API": datetime(2026, 11, 2, 10, 0)}
    hub.entry("demo", "102").seen = ticked

    async def body() -> None:
        tree = add_worktree(repo, "wt")
        write(tree, "progress", "103", "- [ ] one\n")
        await until(lambda: texts(hub, "103") == ["one"])
        # Watched from now on: a tick in it arrives without a restart.
        await asyncio.sleep(0.3)
        write(tree, "progress", "103", "- [x] one\n")
        await until(lambda: hub.entry("demo", "103").tasks[0].state == TaskState.done)
        git(repo, "worktree", "remove", "--force", str(tree))
        await until(lambda: texts(hub, "103") == [])

    events = asyncio.run(watching(hub, body))
    assert {"type": "reload"} in events
    assert hub.entry("demo", "102").seen == ticked  # the full reload keeps the tick times


def test_worktree_without_sprint_gets_one_later(repo: Path, notifier: Recorder) -> None:
    hub = Hub(repo.parent, lambda ended: FakeRunner(ended, delay=0), notifier)
    tree = add_worktree(repo, "wt")

    async def body() -> None:
        await asyncio.sleep(1.2)  # a few polls find a worktree with no `sprint/`: nothing to do
        write(tree, "progress", "103", "- [x] late\n")
        await until(lambda: texts(hub, "103") == ["late"])

    asyncio.run(watching(hub, body))
