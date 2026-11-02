"""scripts/hub-try.sh makes steps a real runner accepts, and --remove takes them away."""

import json
import os
import subprocess
import sys
from pathlib import Path

from hubd import install
from hubd.model import State
from hubd.runners.claude import ClaudeCodeRunner
from hubd.vault import load_vault

SCRIPT = Path(__file__).parents[1] / "scripts" / "hub-try.sh"


def run(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    # A fake `uv`: `uv run hubd import hub-try` runs this python, with no network or real HOME.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    (bin_dir / "uv").write_text(f'#!/bin/sh\nshift 2\nexec {sys.executable} -m hubd "$@"\n')
    (bin_dir / "uv").chmod(0o755)
    env = {
        **os.environ,
        "HOME": str(tmp_path),
        "HUB_VAULT": str(tmp_path / "Hub"),
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
    }
    return subprocess.run([SCRIPT, *args], env=env, capture_output=True, text=True)


def test_creates_then_removes(tmp_path: Path) -> None:
    made = run(tmp_path)
    assert made.returncode == 0, made.stderr
    repo, vault = tmp_path / "tmp" / "hub-try", tmp_path / "Hub"

    index = load_vault(vault)
    assert index.errors == []
    assert index.projects["hub-try"].model == "haiku"
    steps = {e.step.step: e.step for e in index.steps}
    assert list(steps) == ["901", "902", "903"]
    assert all(s.state == State.todo and s.model == "haiku" for s in steps.values())
    assert steps["901"].branch == "step/901-first-note"

    git = ["git", "-C", str(repo)]
    assert subprocess.check_output([*git, "branch", "--show-current"], text=True).strip() == "main"
    assert subprocess.check_output([*git, "status", "--porcelain"], text=True) == ""  # all ignored
    assert "Checklist" in (repo / "CLAUDE.md").read_text()

    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps(install.with_hook({})))
    runner = ClaudeCodeRunner(["term"], "http://x", settings)
    reason = runner.refusal("901", repo, True, None)
    assert reason is None or "claude not on PATH" in reason  # CI has no claude

    again = run(tmp_path)
    assert again.returncode == 1 and "--remove first" in again.stderr
    assert (repo / "CLAUDE.md").exists()

    assert run(tmp_path, "--remove").returncode == 0
    assert not repo.exists() and not (vault / "projects" / "hub-try").exists()
    assert (vault / "projects").is_dir()
