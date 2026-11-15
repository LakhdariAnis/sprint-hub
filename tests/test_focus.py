import subprocess
from pathlib import Path

import pytest

from hubd import focus

SESSION = "3f2a-c91"


def proc(tmp_path: Path, pid: int, parent: int, argv: list[str]) -> None:
    folder = tmp_path / str(pid)
    folder.mkdir()
    (folder / "cmdline").write_bytes(b"\0".join(a.encode() for a in argv))
    (folder / "stat").write_text(f"{pid} (my term) S {parent} 1 1 0\n")  # comm with a space


def test_window_pid_walks_up_to_the_window(tmp_path: Path) -> None:
    proc(tmp_path, 10, 1, ["foot", "--dir=/repo"])  # terminal handed its argv on (no session)
    proc(tmp_path, 20, 10, ["claude", "--session-id", SESSION])
    proc(tmp_path, 30, 1, ["claude", "--session-id", "other"])
    assert focus.window_pid(SESSION, {10, 99}, tmp_path) == 10
    assert focus.window_pid(SESSION, {99}, tmp_path) is None  # not in any window
    assert focus.window_pid("gone", {10}, tmp_path) is None


def test_open_run_focuses_the_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(focus, "_windows", lambda env: {10})
    monkeypatch.setattr(focus, "window_pid", lambda session, windows: 10)
    monkeypatch.setattr(subprocess, "run", lambda argv, **_: calls.append(argv))
    focus.open_run(SESSION, "demo", "102")
    assert calls == [["hyprctl", "dispatch", "focuswindow", "pid:10"]]


def test_open_run_without_terminal_opens_the_app(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(focus, "_windows", lambda env: set())
    monkeypatch.setattr(subprocess, "Popen", lambda argv, **_: calls.append(argv))
    focus.open_run(SESSION, "demo", "102")
    assert calls == [[str(focus.APP), "#/step/demo/102"]]
    assert focus.APP.is_file()
