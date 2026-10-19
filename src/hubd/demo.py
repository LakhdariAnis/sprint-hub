"""`hubd --demo`: the whole loop on built-in data. Never touches the real vault or settings."""

import shutil
import subprocess
import tempfile
from pathlib import Path

from fastapi import FastAPI

from hubd.api import create_app
from hubd.daemon import Hub
from hubd.notify import NullNotifier
from hubd.runners.fake import FakeRunner

# shortcut: the demo data is the test fixture, so it only runs from a source checkout.
FIXTURE = Path(__file__).parents[2] / "tests" / "fixtures" / "vault"


def demo_vault() -> Path:
    """A throwaway vault: the fixture's good projects and a git repo with `main` + one commit."""
    vault = Path(tempfile.mkdtemp(prefix="hubd-demo-"))
    shutil.copytree(FIXTURE, vault, dirs_exist_ok=True)
    shutil.rmtree(vault / "projects" / "broken")
    repo = vault / "demo-repo"
    git = ["git", "-c", "user.name=hubd demo", "-c", "user.email=demo@hubd.invalid"]
    for args in (["init", "-q", "-b", "main"], ["add", "."], ["commit", "-q", "-m", "demo"]):
        subprocess.run([*git, *args], cwd=repo, check=True)
    return vault


def demo_app() -> FastAPI:
    return create_app(Hub(demo_vault(), lambda ended: FakeRunner(ended), NullNotifier()))
