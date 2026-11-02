from importlib.metadata import version
from pathlib import Path

from conftest import Recorder
from fastapi.testclient import TestClient

from hubd.api import create_app
from hubd.daemon import Hub
from hubd.runners.fake import FakeRunner


def test_health() -> None:
    response = TestClient(create_app()).get("/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True, "version": version("hubd"), "demo": False}


def test_health_says_whether_the_vault_is_there(tmp_path: Path) -> None:
    hub = Hub(tmp_path / "Hub", lambda ended: FakeRunner(ended, delay=0), Recorder())
    client = TestClient(create_app(hub))
    body = client.get("/health").json()
    assert (body["vault"], body["vault_found"]) == (str(tmp_path / "Hub"), False)
    (tmp_path / "Hub" / "projects").mkdir(parents=True)
    assert client.get("/health").json()["vault_found"] is True
