import subprocess

import pytest

from hubd import session
from hubd.notify import NotifySend, NullNotifier


def test_notify_send_command(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(subprocess, "Popen", lambda argv, **_: calls.append(argv))
    NotifySend().notify("Run ended", "demo 102")
    assert calls == [["notify-send", "--app-name=sprint-hub", "Run ended", "demo 102"]]


def test_notify_send_gets_the_session_env(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[dict] = []
    monkeypatch.setattr(session, "env", lambda: {"WAYLAND_DISPLAY": "wayland-1"})
    monkeypatch.setattr(subprocess, "Popen", lambda argv, env: seen.append(env))
    NotifySend().notify("t", "b")
    assert seen == [{"WAYLAND_DISPLAY": "wayland-1"}]


def test_notify_send_missing_is_quiet(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(argv: list[str], **_: object) -> None:
        raise FileNotFoundError("notify-send")

    monkeypatch.setattr(subprocess, "Popen", missing)
    NotifySend().notify("t", "b")


def test_null_notifier_does_nothing() -> None:
    NullNotifier().notify("t", "b")
