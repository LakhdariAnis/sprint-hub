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
    return asyncio.run(hub.approve("demo", step_id))


def test_clean_merge(vault: Path, hub: Hub, repo: Path) -> None:
    assert approve(hub).state == State.approved
    assert _load_step(vault / "projects" / "demo" / "steps" / "103.md").state == State.approved
    assert git(repo, "log", "-1", "--format=%s %p").startswith("Merge branch 'step/103-ui'")
    assert len(git(repo, "log", "-1", "--format=%p").split()) == 2  # --no-ff: a real merge commit
    assert (repo / "ui.txt").exists()


def test_dirty_tree_is_refused(hub: Hub, repo: Path) -> None:
    (repo / "notes.txt").write_text("edited\n")
    with pytest.raises(InvalidTransition, match="uncommitted changes"):
        approve(hub)
    assert hub.entry("demo", "103").step.state == State.done


def test_not_on_main_is_refused(hub: Hub, repo: Path) -> None:
    git(repo, "checkout", "-q", "step/103-ui")
    with pytest.raises(InvalidTransition, match="not 'main'"):
        approve(hub)
    assert hub.entry("demo", "103").step.state == State.done


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


def test_diffstat(hub: Hub, repo: Path) -> None:
    client = TestClient(create_app(hub))
    stat = client.get("/steps/demo/103/diffstat").json()["stat"]
    assert "1 file changed" in stat
    assert client.get("/steps/demo/nope/diffstat").status_code == 404
