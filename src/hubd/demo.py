"""`hubd --demo`: the whole loop on built-in data. Never touches the real vault or settings."""

import shutil
import subprocess
import tempfile
from datetime import date, timedelta
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
    "demo-repo/sprint/103-ui.md": "# Step 103 — Show the list\n\n## Tasks\n"
    "- Draw the list\n- Sort it\n",
    "demo-repo/sprint/104-docs.md": "# Step 104 — Write the docs\n\n## Tasks\n"
    "- Write the intro\n- Add the install section\n- Link the API\n",
    "demo-repo/sprint/progress/104.md": "# Step 104\n- [x] Write the intro\n"
    "- [x] Add the install section\n- [x] Link the API\n",
    # Sprint 2 (approved) next to the fixture's sprint 1: two groups for the Project screen to fold.
    "projects/demo/steps/201.md": "---\nstep: 201\ntitle: Tag the release\nstate: approved\n"
    "by: claude\nmodel: sonnet\nsprint: 2\n---\n\n## Runs\n\n## Review\nverdict: approve\n"
    "comment:\n",
    "projects/demo/steps/202.md": "---\nstep: 202\ntitle: Write the changelog\nstate: approved\n"
    "by: claude\nmodel: sonnet\nsprint: 2\n---\n\n## Runs\n\n## Review\nverdict: approve\n"
    "comment:\n",
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

# The `branch:` of each demo step that is not approved yet, per repo.
BRANCHES = {
    "demo-repo": ["step/102-api", "step/103-ui", "step/104-docs"],
    "notes-repo": ["step/301-parse", "step/302-search"],
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
    (vault / "deadlines.md").write_text(demo_deadlines(date.today()))
    for repo, branches in BRANCHES.items():
        cwd = vault / repo
        git(cwd, "init", "-q", "-b", "main")
        git(cwd, "config", "user.name", "hubd demo")  # approve's merge commit needs a name too
        git(cwd, "config", "user.email", "demo@hubd.invalid")
        git(cwd, "add", ".")
        git(cwd, "commit", "-q", "-m", "demo")
        for branch in branches:  # one commit per step branch, so approve has something to merge
            step_id = branch.removeprefix("step/").split("-")[0]
            git(cwd, "checkout", "-q", "-b", branch)
            (cwd / f"work-{step_id}.md").write_text(f"Work of step {step_id}.\n")
            git(cwd, "add", ".")
            git(cwd, "commit", "-q", "-m", f"step {step_id}")
            git(cwd, "checkout", "-q", "main")
    return vault


def demo_deadlines(today: date) -> str:
    """One overdue, one today, one in 3 days, one done: dated from today so the demo never ages."""
    d = [today + timedelta(days=n) for n in (-2, 0, 3, -1)]
    return (
        "# Deadlines\n\n"
        f"- [ ] {d[0]} Compilation TP report #school\n"
        f"- [ ] {d[1]} Fraunhofer IPA application #internship\n"
        f"- [ ] {d[2]} Release notes for the demo #work [[demo/104]]\n"
        f"- [x] {d[3]} PFE topic form #school\n"
    )


def git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True)


def demo_app() -> FastAPI:
    return create_app(Hub(demo_vault(), lambda ended: FakeRunner(ended), NullNotifier()), demo=True)
