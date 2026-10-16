import time
from pathlib import Path

from fastapi.testclient import TestClient

from hubd.api import create_app
from hubd.daemon import Hub
from hubd.model import State
from hubd.vault import _load_step, load_vault


def test_start_runs_to_done(vault: Path, hub: Hub) -> None:
    with TestClient(create_app(hub)) as client:
        response = client.post("/steps/demo/104/start")
        assert response.status_code == 200
        assert response.json()["state"] == "doing"
        deadline = time.monotonic() + 2
        while hub.entry("demo", "104").step.state != State.done:
            assert time.monotonic() < deadline, "FakeRunner did not end the run"
            time.sleep(0.01)
    assert _load_step(vault / "projects" / "demo" / "steps" / "104.md").state == State.done


def test_invalid_start_is_409_with_reason(hub: Hub) -> None:
    client = TestClient(create_app(hub))
    response = client.post("/steps/demo/103/start")
    assert response.status_code == 409
    assert response.json() == {"detail": "step 103: no 'start' from 'done'"}
    assert client.post("/steps/demo/999/start").status_code == 404


def test_run_ended_from_the_hook(hub: Hub) -> None:
    client = TestClient(create_app(hub))
    body = {"session_id": "3f2a…c91", "step": "102"}
    response = client.post("/runs/ended", json=body)
    assert response.status_code == 200
    assert response.json()["state"] == "done"
    again = client.post("/runs/ended", json=body)
    assert again.status_code == 409
    assert "no 'run_ended' from 'done'" in again.json()["detail"]
    assert client.post("/runs/ended", json={"session_id": "x"}).status_code == 422


def test_missing_vault_is_an_error_not_a_crash(tmp_path: Path) -> None:
    index = load_vault(tmp_path / "nothing")
    assert [e.message for e in index.errors] == ["no projects folder"]
