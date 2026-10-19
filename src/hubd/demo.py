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


# Extra demo data on top of the fixture: (path under the vault, text).
EXTRA = {
    "demo-repo/sprint/104-docs.md": "# Step 104 — Write the docs\n\n## Tasks\n"
    "- Write the intro\n- Add the install section\n- Link the API\n",
    "demo-repo/sprint/progress/104.md": "# Step 104\n- [x] Write the intro\n"
    "- [x] Add the install section\n- [x] Link the API\n",
    "projects/notes/project.md": "---\nname: notes\nrepo: notes-repo\nmodel: sonnet\n"
    "merge: manual\n---\nSecond demo project.\n",
    "projects/notes/steps/301.md": "---\nstep: 301\ntitle: Parse the notes\nstate: todo\n"
    "by: claude\nmodel: sonnet\nbranch: step/301-parse\ndue: 2026-10-25\n---\n\n## Runs\n\n"
    "## Review\nverdict:\ncomment:\n\n## Questions\n",
    "projects/notes/steps/302.md": "---\nstep: 302\ntitle: Search the notes\nstate: doing\n"
    "by: claude\nmodel: sonnet\nbranch: step/302-search\nneeds: [301]\n---\n\n## Runs\n"
    "- 2026-10-19 09:00 · sonnet · session 5d4c…b21 · task all\n\n## Review\nverdict:\n"
    "comment:\n\n## Questions\n",
    "notes-repo/sprint/301-parse.md": "# Step 301 — Parse the notes\n\n## Tasks\n"
    "- Read the files\n- Split into sections\n- Test it\n",
    "notes-repo/sprint/302-search.md": "# Step 302 — Search the notes\n\n## Tasks\n"
    "- Index the text\n- Add the query\n",
    "notes-repo/sprint/progress/302.md": "# Step 302\n- [x] Index the text\n- [~] Add the query\n",
}


def demo_vault() -> Path:
    """A throwaway vault: the fixture's good projects, a second project, a git repo for each."""
    vault = Path(tempfile.mkdtemp(prefix="hubd-demo-"))
    shutil.copytree(FIXTURE, vault, dirs_exist_ok=True)
    shutil.rmtree(vault / "projects" / "broken")
    for name, text in EXTRA.items():
        path = vault / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    git = ["git", "-c", "user.name=hubd demo", "-c", "user.email=demo@hubd.invalid"]
    for repo in ("demo-repo", "notes-repo"):
        for args in (["init", "-q", "-b", "main"], ["add", "."], ["commit", "-q", "-m", "demo"]):
            subprocess.run([*git, *args], cwd=vault / repo, check=True)
    return vault


def demo_app() -> FastAPI:
    return create_app(Hub(demo_vault(), lambda ended: FakeRunner(ended), NullNotifier()))
