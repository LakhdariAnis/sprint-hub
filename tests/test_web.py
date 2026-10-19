from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hubd import api


def test_root_serves_built_index(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "index.html").write_text("<div id=app></div>")
    monkeypatch.setattr(api, "WEB_DIST", tmp_path)
    client = TestClient(api.create_app())
    assert client.get("/").text == "<div id=app></div>"
    assert client.get("/health").json()["ok"] is True


def test_root_says_how_to_build(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api, "WEB_DIST", tmp_path / "missing")
    response = TestClient(api.create_app()).get("/")
    assert response.status_code == 200
    assert "npm run build" in response.text
