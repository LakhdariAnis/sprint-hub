"""Refused starts of the real runner: a fake spawn, a small vault, real files."""

import asyncio
import json
import subprocess
from pathlib import Path

import pytest
from conftest import Recorder

from hubd import install
from hubd.daemon import Hub
from hubd.model import State
from hubd.runners import claude
from hubd.runners.claude import ClaudeCodeRunner
from hubd.states import InvalidTransition

URL = "http://127.0.0.1:8765"


class Launched:
    def __init__(self, code: int | None = None):
        self.code = code

    def poll(self) -> int | None:
        return self.code


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Vault project `try` with todo steps 901 and 902; spec and command in the repo."""
    repo = tmp_path / "repo"
    for step in ("901", "902"):
        folder = tmp_path / "projects" / "try" / "steps"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{step}.md").write_text(
            f"---\nstep: {step}\ntitle: Note\nstate: todo\nby: claude\n---\n\n"
            "## Runs\n\n## Review\nverdict:\ncomment:\n"
        )
        for path, text in (
            (f"sprint/{step}-note.md", f"# Step {step} — Note\n"),
            (f".claude/commands/sprint-{step}.md", "---\nmodel: haiku\n---\nGo\n"),
        ):
            (repo / path).parent.mkdir(parents=True, exist_ok=True)
            (repo / path).write_text(text)
    (tmp_path / "projects" / "try" / "project.md").write_text(
        f"---\nname: try\nrepo: {repo}\nmodel: sonnet\nmerge: manual\n---\n"
    )
    return repo


@pytest.fixture
def spawned(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[list[str]]:
    """`claude` on PATH, a Popen that only records its argv."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "claude").write_text("#!/bin/sh\n")
    (bin_dir / "claude").chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir))
    monkeypatch.setattr(claude, "GRACE", 0)
    calls: list[list[str]] = []

    def popen(argv: list[str], **_: object) -> Launched:
        calls.append(argv)
        return Launched()

    monkeypatch.setattr(subprocess, "Popen", popen)
    return calls


@pytest.fixture
def hub(tmp_path: Path, repo: Path, spawned: list[list[str]]) -> Hub:
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps(install.with_hook({})))
    runner = ClaudeCodeRunner(["term", "{cwd}"], URL, settings)
    return Hub(tmp_path, lambda _: runner, Recorder())


def step_file(hub: Hub, step: str = "901") -> Path:
    return hub.vault / "projects" / "try" / "steps" / f"{step}.md"


def refused(hub: Hub, match: str, spawned: list[list[str]], *, spawns: int = 0) -> None:
    """Start 901: refused with `match`, step file and index as they were."""
    before = step_file(hub).read_bytes()
    with pytest.raises(InvalidTransition, match=match):
        asyncio.run(hub.start("try", "901"))
    assert step_file(hub).read_bytes() == before
    assert hub.entry("try", "901").step.state == State.todo
    assert hub.entry("try", "901").step.runs == []
    assert len(spawned) == spawns


def test_good_start_opens_the_terminal(hub: Hub, repo: Path, spawned: list[list[str]]) -> None:
    step = asyncio.run(hub.start("try", "901"))
    assert step.state == State.doing
    [argv] = spawned
    assert argv[:3] == ["term", str(repo), "claude"]
    assert argv[-1] == "/sprint-901"
    assert "state: doing" in step_file(hub).read_text()


def test_no_command_file(hub: Hub, repo: Path, spawned: list[list[str]]) -> None:
    (repo / ".claude/commands/sprint-901.md").unlink()
    refused(hub, "sprint-901.md", spawned)


def test_claude_not_on_path(
    hub: Hub, spawned: list[list[str]], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path / "nowhere"))
    refused(hub, "claude not on PATH", spawned)


def test_hook_missing(hub: Hub, tmp_path: Path, spawned: list[list[str]]) -> None:
    (tmp_path / "settings.json").write_text("{}")
    refused(hub, "hook missing: run hubd install-hook", spawned)


def test_terminal_not_found(
    hub: Hub, spawned: list[list[str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    def popen(*_: object, **__: object) -> None:
        raise FileNotFoundError(2, "No such file or directory", "term")

    monkeypatch.setattr(subprocess, "Popen", popen)
    refused(hub, "terminal did not launch.*term", spawned)


def test_terminal_exits_with_an_error(hub: Hub, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(subprocess, "Popen", lambda *_, **__: Launched(2))
    refused(hub, "terminal term exited with code 2", [])


def test_terminal_handing_off_to_a_running_instance_is_fine(
    hub: Hub, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(subprocess, "Popen", lambda *_, **__: Launched(0))
    assert asyncio.run(hub.start("try", "901")).state == State.doing
