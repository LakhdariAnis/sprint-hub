import asyncio
import json
import shlex
import subprocess
from pathlib import Path

import pytest

from hubd.model import Step
from hubd.runners import claude
from hubd.runners.base import Unavailable
from hubd.runners.claude import ClaudeCodeRunner
from hubd.settings import Settings
from hubd.states import InvalidTransition

STEP = Step(step="106", title="State table", state="todo")
SESSION = "550e8400-e29b-41d4-a716-446655440000"
URL = "http://127.0.0.1:8765"


class Launched:
    """A Popen whose terminal is still open."""

    def poll(self) -> None:
        return None


@pytest.fixture
def spawned(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    calls: list[dict] = []

    def popen(argv: list[str], **kw: object) -> Launched:
        calls.append({"argv": argv, **kw})
        return Launched()

    monkeypatch.setattr(subprocess, "Popen", popen)
    monkeypatch.setattr(claude, "GRACE", 0)
    return calls


def test_start_command_and_env(spawned: list[dict], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", "/home/x")
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-1")  # set: session.env() asks no systemctl
    runner = ClaudeCodeRunner(Settings().terminal, URL)
    asyncio.run(runner.start(STEP, SESSION, "opus", Path("/repo"), "/sprint-106"))
    [call] = spawned
    assert call["argv"] == [
        "xdg-terminal-exec",
        "--dir=/repo",
        "claude",
        "--model",
        "opus",
        "--session-id",
        SESSION,
        "/sprint-106",
    ]
    assert call["cwd"] == Path("/repo")
    assert call["env"]["HUB_RUN"] == "106"
    assert call["env"]["HUB_URL"] == URL
    assert call["env"]["HOME"] == "/home/x"  # the rest of the env is kept
    assert call["env"]["WAYLAND_DISPLAY"] == "wayland-1"
    assert call["start_new_session"] is True


def test_resume_command(spawned: list[dict]) -> None:
    runner = ClaudeCodeRunner(["foot", "-D", "{cwd}"], URL)
    asyncio.run(runner.resume(STEP, SESSION, Path("/repo"), "fix the review"))
    [call] = spawned
    assert call["argv"] == ["foot", "-D", "/repo", "claude", "--resume", SESSION, "fix the review"]
    assert call["env"]["HUB_RUN"] == "106"


def test_resume_without_a_prompt_passes_none(spawned: list[dict]) -> None:
    runner = ClaudeCodeRunner(["foot", "-D", "{cwd}"], URL)
    asyncio.run(runner.resume(STEP, SESSION, Path("/repo"), ""))
    [call] = spawned
    assert call["argv"] == ["foot", "-D", "/repo", "claude", "--resume", SESSION]


def test_never_skips_permissions(spawned: list[dict]) -> None:
    runner = ClaudeCodeRunner(Settings().terminal, URL)
    asyncio.run(runner.start(STEP, SESSION, "opus", Path("/repo"), "go"))
    asyncio.run(runner.resume(STEP, SESSION, Path("/repo"), "go"))
    assert not any("dangerously" in arg for call in spawned for arg in call["argv"])


class Hypr(list):
    """The `hyprctl` calls; `out` is what it prints."""

    out = "ok\n"


@pytest.fixture
def hypr(monkeypatch: pytest.MonkeyPatch) -> Hypr:
    """`hyprctl` on PATH (so is the terminal); stdout is `ok` unless a test says otherwise."""
    calls = Hypr()
    monkeypatch.setattr(claude.shutil, "which", lambda exe: f"/usr/bin/{exe}")

    def run(argv: list[str], **kw: object) -> subprocess.CompletedProcess:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, calls.out, "")

    monkeypatch.setattr(subprocess, "run", run)
    return calls


def test_command_without_workspace_is_unchanged(hypr: Hypr) -> None:
    runner = ClaudeCodeRunner(["foot", "-D", "{cwd}"], URL)
    assert runner.command(STEP, Path("/repo"), ["go"]) == ["foot", "-D", "/repo", "claude", "go"]


def test_command_with_workspace_goes_through_hyprctl(hypr: Hypr) -> None:
    runner = ClaudeCodeRunner(["foot", "-D", "{cwd}"], URL)
    assert runner.command(STEP, Path("/repo"), ["go"], 3) == [
        "hyprctl",
        "dispatch",
        f'hl.dsp.exec_cmd("env HUB_RUN=106 HUB_URL={URL} foot -D /repo claude go", '
        '{ workspace = "3 silent" })',
    ]


def test_command_quotes_a_path_with_spaces(hypr: Hypr) -> None:
    runner = ClaudeCodeRunner(["xdg-terminal-exec", "--dir={cwd}"], URL)
    lua = runner.command(STEP, Path("/my repo/it's"), ["a b"], 4)[2]
    assert lua.endswith(', { workspace = "4 silent" })')
    line = json.loads(lua.removeprefix("hl.dsp.exec_cmd(").rpartition(", {")[0])
    assert shlex.split(line)[3:] == ["xdg-terminal-exec", "--dir=/my repo/it's", "claude", "a b"]


def test_no_hyprctl_on_path_launches_directly(
    spawned: list[dict], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(claude.shutil, "which", lambda exe: None)
    runner = ClaudeCodeRunner(["foot", "-D", "{cwd}"], URL)
    asyncio.run(runner.start(STEP, SESSION, "opus", Path("/repo"), "go", 3))
    assert spawned[0]["argv"][0] == "foot"


def test_start_and_resume_use_hyprctl(hypr: Hypr, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = ClaudeCodeRunner(["foot", "-D", "{cwd}"], URL)
    asyncio.run(runner.start(STEP, SESSION, "opus", Path("/repo"), "go", 3))
    asyncio.run(runner.resume(STEP, SESSION, Path("/repo"), "fix", 3))
    assert [c[2].startswith("hl.dsp.exec_cmd(") for c in hypr] == [True, True]
    assert f"--session-id {SESSION}" in hypr[0][2]
    assert f"--resume {SESSION}" in hypr[1][2]


def test_hyprctl_error_output_raises(hypr: Hypr) -> None:
    hypr.out = "Invalid dispatcher\n"
    runner = ClaudeCodeRunner(["foot", "-D", "{cwd}"], URL)
    with pytest.raises(InvalidTransition, match="hyprctl said Invalid dispatcher"):
        asyncio.run(runner.start(STEP, SESSION, "opus", Path("/repo"), "go", 3))


def test_missing_terminal_raises_with_workspace(
    hypr: Hypr, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(claude.shutil, "which", lambda exe: None if exe == "nope" else "/bin/x")
    runner = ClaudeCodeRunner(["nope", "{cwd}"], URL)
    with pytest.raises(InvalidTransition, match="nope not on PATH"):
        asyncio.run(runner.start(STEP, SESSION, "opus", Path("/repo"), "go", 3))
    assert hypr == []


def test_focus_dispatches_the_workspace(hypr: Hypr) -> None:
    asyncio.run(ClaudeCodeRunner(["foot"], URL).focus(3))
    assert hypr == [["hyprctl", "dispatch", 'hl.dsp.focus({ workspace = "3" })']]


def test_focus_without_hyprctl_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(claude.shutil, "which", lambda exe: None)
    with pytest.raises(Unavailable, match="hyprctl not on PATH"):
        asyncio.run(ClaudeCodeRunner(["foot"], URL).focus(3))


def test_focus_refused_is_unavailable(hypr: Hypr) -> None:
    hypr.out = "Invalid dispatcher\n"
    with pytest.raises(Unavailable, match="hyprctl said Invalid dispatcher"):
        asyncio.run(ClaudeCodeRunner(["foot"], URL).focus(3))
