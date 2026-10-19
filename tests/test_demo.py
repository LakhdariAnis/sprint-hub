import subprocess
import time

from fastapi.testclient import TestClient

from hubd.demo import demo_app, demo_vault


def test_demo_vault_is_a_git_repo_without_broken() -> None:
    vault = demo_vault()
    assert not (vault / "projects" / "broken").exists()
    out = subprocess.run(
        ["git", "log", "--format=%D"], cwd=vault / "demo-repo", capture_output=True, text=True
    )
    assert "main" in out.stdout


def test_demo_lists_projects_and_start_runs_fake_runner() -> None:
    with TestClient(demo_app()) as client:
        assert [p["id"] for p in client.get("/projects").json()] == ["demo", "notes"]
        states = {
            s["state"] for p in ("demo", "notes") for s in client.get(f"/projects/{p}/steps").json()
        }
        assert states == {"todo", "doing", "done", "changes", "approved"}
        assert client.post("/steps/demo/104/start").json()["state"] == "doing"
        deadline = time.monotonic() + 5
        while client.get("/steps/demo/104").json()["state"] != "done":
            assert time.monotonic() < deadline, "FakeRunner did not end the run"
            time.sleep(0.05)
