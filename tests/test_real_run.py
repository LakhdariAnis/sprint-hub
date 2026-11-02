"""Step 506b: a run always gets out of `doing`, and its checklist ticks wherever it works."""

from pathlib import Path

from conftest import Recorder
from fastapi.testclient import TestClient

from hubd.api import create_app
from hubd.daemon import Hub
from hubd.model import State
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
