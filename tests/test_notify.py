import subprocess

import pytest

from hubd.notify import NotifySend, NullNotifier


def test_notify_send_command(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(subprocess, "Popen", lambda argv: calls.append(argv))
    NotifySend().notify("Run ended", "demo 102")
    assert calls == [["notify-send", "--app-name=sprint-hub", "Run ended", "demo 102"]]


def test_notify_send_missing_is_quiet(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(argv: list[str]) -> None:
        raise FileNotFoundError("notify-send")

    monkeypatch.setattr(subprocess, "Popen", missing)
    NotifySend().notify("t", "b")


def test_null_notifier_does_nothing() -> None:
    NullNotifier().notify("t", "b")
