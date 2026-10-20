from importlib.metadata import version

from fastapi.testclient import TestClient

from hubd.api import create_app


def test_health() -> None:
    response = TestClient(create_app()).get("/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True, "version": version("hubd"), "demo": False}
