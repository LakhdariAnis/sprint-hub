from pathlib import Path

from conftest import Recorder
from fastapi.testclient import TestClient

from hubd.api import create_app
from hubd.daemon import Hub
from hubd.runners.fake import FakeRunner


def test_projects(hub: Hub) -> None:
    response = TestClient(create_app(hub)).get("/projects")
    assert response.status_code == 200
    assert response.json() == [
        {"id": "broken", "name": "broken", "repo": None, "model": "sonnet", "merge": "manual"},
        {"id": "demo", "name": "demo", "repo": "demo-repo", "model": "sonnet", "merge": "manual"},
    ]


def test_project_steps(hub: Hub) -> None:
    client = TestClient(create_app(hub))
    steps = client.get("/projects/demo/steps").json()
    assert [(s["step"], s["state"]) for s in steps] == [
        ("101", "todo"),
        ("102", "doing"),
        ("103", "done"),
        ("104", "changes"),
        ("105", "approved"),
    ]
    assert steps[1]["tasks"] == [
        {"text": "Add the FastAPI app", "state": "done"},
        {"text": "Serve `/health`", "state": "doing"},
        {"text": "Test it", "state": "todo"},
    ]
    assert client.get("/projects/nope/steps").status_code == 404


def test_one_step_has_spec_checklist_runs_review(hub: Hub) -> None:
    client = TestClient(create_app(hub))
    step = client.get("/steps/demo/102").json()
    assert step["spec"].startswith("# Step 102 — Serve the API\n")
    assert len(step["tasks"]) == 3
    assert step["runs"][0]["session"] == "3f2a…c91"
    assert step["review"] == {"verdict": None, "comment": ""}
    assert client.get("/steps/demo/101").json()["spec"] is None
    assert client.get("/steps/demo/999").status_code == 404


def ids(steps: list[dict]) -> list[str]:
    return [s["step"] for s in steps]


def test_today(vault: Path) -> None:
    steps = vault / "projects" / "demo" / "steps"
    # 106 needs 104, which is not approved: blocked, so not in "next".
    (steps / "106.md").write_text("---\nstep: 106\ntitle: Later\nstate: todo\nneeds: [104]\n---\n")
    # 107 needs only approved 105, and has a due date: first in "next".
    (steps / "107.md").write_text(
        "---\nstep: 107\ntitle: Soon\nstate: todo\nneeds: [105]\ndue: 2026-10-20\n---\n"
    )
    hub = Hub(vault, lambda ended: FakeRunner(ended, delay=0), Recorder())
    today = TestClient(create_app(hub)).get("/today").json()
    assert ids(today["running"]) == ["102"]
    assert ids(today["review"]) == ["103"]
    assert ids(today["next"]) == ["107", "101", "104"]
