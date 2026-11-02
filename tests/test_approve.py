import asyncio
import subprocess
from pathlib import Path

import pytest
from conftest import Recorder
from fastapi.testclient import TestClient

from hubd.api import create_app
from hubd.daemon import Hub, MergeConflict
from hubd.model import State
from hubd.states import InvalidTransition
from hubd.vault import _load_step


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def repo(vault: Path) -> Path:
    """The fixture's demo-repo as a git repo on main, with branch step/103-ui (103 is `done`)."""
    repo = vault / "demo-repo"
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.name", "test")
    git(repo, "config", "user.email", "test@hubd.invalid")
    (repo / "notes.txt").write_text("main\n")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "start")
    git(repo, "checkout", "-q", "-b", "step/103-ui")
    (repo / "ui.txt").write_text("ui\n")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "ui")
    git(repo, "checkout", "-q", "main")
    return repo


def approve(hub: Hub, step_id: str = "103"):
    return asyncio.run(hub.approve("demo", step_id))[0]


def test_clean_merge(vault: Path, hub: Hub, repo: Path) -> None:
    assert approve(hub).state == State.approved
    assert _load_step(vault / "projects" / "demo" / "steps" / "103.md").state == State.approved
    assert git(repo, "log", "-1", "--format=%s %p").startswith("Merge branch 'step/103-ui'")
    assert len(git(repo, "log", "-1", "--format=%p").split()) == 2  # --no-ff: a real merge commit
    assert (repo / "ui.txt").exists()


def repo_state(repo: Path) -> tuple[str, str, str]:
    """Branch, commit and `git status`: a refusal leaves all three as they were."""
    return (
        git(repo, "branch", "--show-current"),
        git(repo, "rev-parse", "HEAD"),
        git(repo, "status", "--porcelain"),
    )


def refused(hub: Hub, repo: Path, reason: str) -> None:
    before = repo_state(repo)
    with pytest.raises(InvalidTransition, match=reason):
        approve(hub)
    assert repo_state(repo) == before
    assert hub.entry("demo", "103").step.state == State.done
    assert _load_step(hub.entry("demo", "103").path).state == State.done


def test_tracked_changes_are_refused_and_named(hub: Hub, repo: Path) -> None:
    (repo / "notes.txt").write_text("edited\n")
    refused(hub, repo, "uncommitted changes in notes.txt")
    assert (repo / "notes.txt").read_text() == "edited\n"


def test_staged_changes_are_refused(hub: Hub, repo: Path) -> None:
    (repo / "notes.txt").write_text("edited\n")
    git(repo, "add", "notes.txt")
    refused(hub, repo, "uncommitted changes in notes.txt")


def test_tracked_changes_on_the_step_branch_are_refused(hub: Hub, repo: Path) -> None:
    git(repo, "checkout", "-q", "step/103-ui")
    (repo / "ui.txt").write_text("edited\n")
    refused(hub, repo, "uncommitted changes in ui.txt")
    assert (repo / "ui.txt").read_text() == "edited\n"


def test_untracked_files_do_not_block_and_stay(hub: Hub, repo: Path) -> None:
    (repo / "scratch.txt").write_text("mine\n")
    assert approve(hub).state == State.approved
    assert (repo / "scratch.txt").read_text() == "mine\n"


def test_other_branch_is_refused_and_named(hub: Hub, repo: Path) -> None:
    git(repo, "checkout", "-q", "-b", "other")
    refused(hub, repo, "on branch 'other'")


def test_detached_head_is_refused(hub: Hub, repo: Path) -> None:
    git(repo, "checkout", "-q", "--detach")
    refused(hub, repo, "not on a branch")


def test_from_the_step_branch_it_switches_to_base(hub: Hub, repo: Path) -> None:
    git(repo, "checkout", "-q", "step/103-ui")
    assert approve(hub).state == State.approved
    assert git(repo, "branch", "--show-current") == "main"
    assert git(repo, "log", "-1", "--format=%s").startswith("Merge branch 'step/103-ui'")


def set_step(hub: Hub, step_id: str, old: str, new: str) -> Hub:
    """Edit a step file and read the vault again."""
    path = hub.entry("demo", step_id).path
    assert old in path.read_text()
    path.write_text(path.read_text().replace(old, new))
    return Hub(hub.vault, lambda _: hub.runner, hub.notifier)


def test_claude_step_with_no_branch_is_refused(hub: Hub, repo: Path) -> None:
    hub = set_step(hub, "103", "branch: step/103-ui\n", "")
    refused(hub, repo, "no branch to merge")


def test_missing_branch_is_refused(hub: Hub, repo: Path) -> None:
    git(repo, "branch", "-m", "step/103-ui", "gone")
    refused(hub, repo, "branch 'step/103-ui' does not exist")


def test_missing_base_is_refused(vault: Path, hub: Hub, repo: Path) -> None:
    project = vault / "projects/demo/project.md"
    project.write_text(project.read_text().replace("model:", "base: nope\nmodel:", 1))
    hub = Hub(hub.vault, lambda _: hub.runner, hub.notifier)
    refused(hub, repo, "branch 'nope' does not exist")


def test_missing_repo_is_refused(vault: Path, hub: Hub, repo: Path) -> None:
    repo.rename(vault / "moved")
    with pytest.raises(InvalidTransition, match="does not exist"):
        approve(hub)
    assert hub.entry("demo", "103").step.state == State.done


def test_manual_step_without_a_branch_needs_no_git(hub: Hub, repo: Path) -> None:
    hub = set_step(hub, "103", "by: claude\nmodel: sonnet\nbranch: step/103-ui\n", "by: me\n")
    head = git(repo, "rev-parse", "HEAD")
    step, commit = asyncio.run(hub.approve("demo", "103"))
    assert (step.state, commit) == (State.approved, None)
    assert git(repo, "rev-parse", "HEAD") == head


def test_conflict_aborts_and_notifies(
    vault: Path, hub: Hub, repo: Path, notifier: Recorder
) -> None:
    (repo / "ui.txt").write_text("other\n")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "clash")
    with pytest.raises(MergeConflict) as exc:
        approve(hub)
    assert exc.value.files == ["ui.txt"]
    assert git(repo, "status", "--porcelain") == ""  # merge aborted, tree clean
    assert hub.entry("demo", "103").step.state == State.done
    assert _load_step(vault / "projects" / "demo" / "steps" / "103.md").state == State.done
    assert notifier.sent == [("Merge conflict", "demo 103: ui.txt")]


def clash(repo: Path) -> None:
    (repo / "ui.txt").write_text("other\n")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "clash")


def test_conflict_from_the_step_branch_goes_back_to_it(
    vault: Path, hub: Hub, repo: Path, notifier: Recorder
) -> None:
    clash(repo)
    git(repo, "checkout", "-q", "step/103-ui")
    before = repo_state(repo)
    with pytest.raises(MergeConflict, match="conflict in ui.txt"):
        approve(hub)
    assert repo_state(repo) == before
    assert not (repo / ".git/MERGE_HEAD").exists()
    assert hub.entry("demo", "103").step.state == State.done
    assert notifier.sent == [("Merge conflict", "demo 103: ui.txt")]


def test_conflict_keeps_untracked_files(hub: Hub, repo: Path) -> None:
    clash(repo)
    (repo / "scratch.txt").write_text("mine\n")
    with pytest.raises(MergeConflict):
        approve(hub)
    assert (repo / "scratch.txt").read_text() == "mine\n"


def test_untracked_file_in_the_way_changes_nothing(hub: Hub, repo: Path) -> None:
    (repo / "ui.txt").write_text("mine\n")
    refused(hub, repo, "would be overwritten")
    assert (repo / "ui.txt").read_text() == "mine\n"


def test_untracked_file_in_the_way_of_the_switch_changes_nothing(hub: Hub, repo: Path) -> None:
    git(repo, "checkout", "-q", "main")
    (repo / "base.txt").write_text("base\n")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "base")
    git(repo, "checkout", "-q", "step/103-ui")
    (repo / "base.txt").write_text("mine\n")
    refused(hub, repo, "would be overwritten")
    assert (repo / "base.txt").read_text() == "mine\n"


def test_merge_stopped_by_a_hook_changes_nothing(hub: Hub, repo: Path) -> None:
    hook = repo / ".git/hooks/pre-merge-commit"
    hook.write_text("#!/bin/sh\necho no merges today\nexit 1\n")
    hook.chmod(0o755)
    git(repo, "checkout", "-q", "step/103-ui")
    refused(hub, repo, "no merges today")
    assert not (repo / ".git/MERGE_HEAD").exists()


def test_wrong_state_is_refused(hub: Hub, repo: Path) -> None:
    head = git(repo, "rev-parse", "HEAD")
    with pytest.raises(InvalidTransition, match="no 'approve' from 'changes'"):
        approve(hub, "104")
    assert git(repo, "rev-parse", "HEAD") == head


def test_api_approve_and_conflict(hub: Hub, repo: Path) -> None:
    client = TestClient(create_app(hub))
    assert client.post("/steps/demo/104/approve").status_code == 409
    (repo / "ui.txt").write_text("other\n")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "clash")
    response = client.post("/steps/demo/103/approve")
    assert response.status_code == 409
    assert response.json()["files"] == ["ui.txt"]
    git(repo, "reset", "-q", "--hard", "HEAD~1")
    response = client.post("/steps/demo/103/approve")
    assert response.status_code == 200
    assert response.json()["state"] == "approved"


def test_api_says_the_merge_commit_and_the_base(hub: Hub, repo: Path) -> None:
    client = TestClient(create_app(hub))
    assert client.get("/steps/demo/103").json()["base"] == "main"
    commit = client.post("/steps/demo/103/approve").json()["commit"]
    assert commit == git(repo, "rev-parse", "--short", "main")
    assert len(git(repo, "log", "-1", "--format=%p", commit).split()) == 2


def test_diffstat(hub: Hub, repo: Path) -> None:
    client = TestClient(create_app(hub))
    stat = client.get("/steps/demo/103/diffstat").json()["stat"]
    assert "1 file changed" in stat
    assert client.get("/steps/demo/nope/diffstat").status_code == 404


def test_base_other_than_main(vault: Path, hub: Hub, repo: Path) -> None:
    git(repo, "switch", "-q", "-c", "v2", "main")
    (repo / "v2.txt").write_text("v2\n")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "v2")
    project = vault / "projects/demo/project.md"
    project.write_text(project.read_text().replace("model:", "base: v2\nmodel:", 1))
    hub = Hub(hub.vault, lambda _: hub.runner, hub.notifier)
    assert "ui.txt" in asyncio.run(hub.diffstat("demo", "103"))
    assert approve(hub).state == State.approved
    assert git(repo, "branch", "--show-current") == "v2"
    assert "ui.txt" in git(repo, "ls-tree", "--name-only", "v2")
    assert "ui.txt" not in git(repo, "ls-tree", "--name-only", "main")
