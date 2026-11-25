import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hubd.api import create_app
from hubd.daemon import Hub
from hubd.runners import claude
from hubd.runners.claude import ClaudeCodeRunner
from hubd.runners.fake import FakeRunner


def with_workspace(vault: Path, project: str = "demo") -> None:
    path = vault / "projects" / project / "project.md"
    path.write_text(path.read_text().replace("model: sonnet", "model: sonnet\nworkspace: 3", 1))


def test_focus_switches_to_the_workspace(vault: Path, notifier) -> None:
    with_workspace(vault)
    hub = Hub(vault, lambda ended: FakeRunner(ended, delay=0), notifier)
    response = TestClient(create_app(hub)).post("/projects/demo/focus")
    assert (response.status_code, response.json()) == (200, {"workspace": 3})
    assert hub.runner.focused == [3]  # type: ignore[attr-defined]


def test_focus_without_a_workspace_is_404(hub: Hub) -> None:
    response = TestClient(create_app(hub)).post("/projects/demo/focus")
    assert response.status_code == 404
    assert "demo has no workspace" in response.json()["detail"]
    assert hub.runner.focused == []  # type: ignore[attr-defined]


def test_focus_unknown_project_is_404(hub: Hub) -> None:
    assert TestClient(create_app(hub)).post("/projects/nope/focus").status_code == 404


def test_focus_without_hyprctl_is_503(
    vault: Path, notifier, monkeypatch: pytest.MonkeyPatch
) -> None:
    with_workspace(vault)
    monkeypatch.setattr(claude.shutil, "which", lambda exe: None)
    hub = Hub(vault, lambda ended: ClaudeCodeRunner(["foot"], "http://hub"), notifier)
    response = TestClient(create_app(hub)).post("/projects/demo/focus")
    assert response.status_code == 503
    assert "hyprctl not on PATH" in response.json()["detail"]


def test_focus_runs_hyprctl(vault: Path, notifier, monkeypatch: pytest.MonkeyPatch) -> None:
    with_workspace(vault)
    calls: list[list[str]] = []
    monkeypatch.setattr(claude.shutil, "which", lambda exe: f"/usr/bin/{exe}")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda argv, **kw: calls.append(argv) or subprocess.CompletedProcess(argv, 0, "ok\n", ""),
    )
    hub = Hub(vault, lambda ended: ClaudeCodeRunner(["foot"], "http://hub"), notifier)
    assert TestClient(create_app(hub)).post("/projects/demo/focus").status_code == 200
    assert calls == [["hyprctl", "dispatch", 'hl.dsp.focus({ workspace = "3" })']]


def test_patch_sets_and_clears_the_workspace(vault: Path, hub: Hub) -> None:
    path = vault / "projects" / "demo" / "project.md"
    client = TestClient(create_app(hub))
    response = client.patch("/projects/demo", json={"workspace": 4})
    assert response.status_code == 200
    assert response.json() == {
        "workspace": 4,
        "account": "claude",
        "archived": False,
        "graph": False,
    }
    assert "workspace: 4" in path.read_text()
    assert client.patch("/projects/demo", json={"workspace": 5}).json()["workspace"] == 5
    assert path.read_text().count("workspace:") == 1
    assert client.patch("/projects/demo", json={"workspace": None}).json()["workspace"] is None
    assert "workspace" not in path.read_text()


def test_patch_sets_the_account_and_keeps_the_workspace(vault: Path, hub: Hub) -> None:
    path = vault / "projects" / "demo" / "project.md"
    client = TestClient(create_app(hub))
    client.patch("/projects/demo", json={"workspace": 4})
    assert client.patch("/projects/demo", json={"account": "personal"}).json() == {
        "workspace": 4,
        "account": "personal",
        "archived": False,
        "graph": False,
    }
    assert "account: personal" in path.read_text()
    assert client.patch("/projects/demo", json={"account": "claude"}).json()["account"] == "claude"
    assert "account" not in path.read_text()
    assert client.patch("/projects/demo", json={"account": "x"}).status_code == 422


def test_patch_archives_and_unarchives(vault: Path, hub: Hub) -> None:
    path = vault / "projects" / "demo" / "project.md"
    client = TestClient(create_app(hub))
    assert client.patch("/projects/demo", json={"archived": True}).json()["archived"] is True
    assert "archived: true" in path.read_text()
    assert {p["id"]: p["archived"] for p in client.get("/projects").json()}["demo"] is True
    assert client.patch("/projects/demo", json={"archived": False}).json()["archived"] is False
    assert "archived" not in path.read_text()


@pytest.mark.parametrize("bad", [1, 10, "x"])
def test_patch_refuses_a_bad_workspace(hub: Hub, bad: object) -> None:
    response = TestClient(create_app(hub)).patch("/projects/demo", json={"workspace": bad})
    assert response.status_code == 422


def test_patch_unknown_project_is_404(hub: Hub) -> None:
    response = TestClient(create_app(hub)).patch("/projects/nope", json={"workspace": 3})
    assert response.status_code == 404
