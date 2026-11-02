import asyncio
import subprocess
from pathlib import Path

import pytest

from hubd.model import Step
from hubd.runners import claude
from hubd.runners.claude import ClaudeCodeRunner
from hubd.settings import Settings

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


def test_never_skips_permissions(spawned: list[dict]) -> None:
    runner = ClaudeCodeRunner(Settings().terminal, URL)
    asyncio.run(runner.start(STEP, SESSION, "opus", Path("/repo"), "go"))
    asyncio.run(runner.resume(STEP, SESSION, Path("/repo"), "go"))
    assert not any("dangerously" in arg for call in spawned for arg in call["argv"])
