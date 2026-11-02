import subprocess

import pytest

from hubd import session


def test_env_untouched_with_a_display(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-9")

    def boom(*_a, **_k):
        raise AssertionError("systemctl called")

    monkeypatch.setattr(subprocess, "run", boom)
    assert session.env()["WAYLAND_DISPLAY"] == "wayland-9"


def test_env_fills_from_user_manager(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setenv("PATH", "/mine")
    shown = "WAYLAND_DISPLAY=wayland-1\nPATH=/manager\nA=b=c\n"
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, shown, "")
    )
    env = session.env()
    assert env["WAYLAND_DISPLAY"] == "wayland-1"
    assert env["PATH"] == "/mine"  # what the process has wins
    assert env["A"] == "b=c"


def test_env_without_systemctl(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)

    def missing(*_a, **_k):
        raise FileNotFoundError

    monkeypatch.setattr(subprocess, "run", missing)
    assert "WAYLAND_DISPLAY" not in session.env()
