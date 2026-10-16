import re
from datetime import date, datetime
from pathlib import Path

import frontmatter
import pytest
from pydantic import ValidationError

from hubd.model import Merge, Project, Review, Run, State, Step, Task, TaskState

VAULT = Path(__file__).parent / "fixtures" / "vault"
DEMO = VAULT / "projects" / "demo"


def test_project_parses() -> None:
    project = Project.model_validate(frontmatter.load(DEMO / "project.md").metadata)
    assert project == Project(
        name="demo", repo=Path("demo-repo"), model="sonnet", merge=Merge.manual
    )


def test_one_step_file_per_state() -> None:
    paths = sorted((DEMO / "steps").glob("*.md"))
    steps = [Step.model_validate(frontmatter.load(p).metadata) for p in paths]
    assert [s.state for s in steps] == list(State)
    assert [s.step for s in steps] == [p.stem for p in paths]


def test_step_fields() -> None:
    todo = Step.model_validate(frontmatter.load(DEMO / "steps" / "101.md").metadata)
    assert (todo.by, todo.model, todo.branch, todo.needs) == ("me", None, None, [])

    doing = Step.model_validate(frontmatter.load(DEMO / "steps" / "102.md").metadata)
    assert doing.needs == ["101"]
    assert doing.due == date(2026, 10, 24)


def test_unknown_state_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Step.model_validate({"step": "1", "title": "x", "state": "blocked"})


# Runs and Review live in the body; the section parser comes in step 104.
# These are the values of steps/104.md.
def test_run_and_review() -> None:
    run = Run.model_validate(
        {
            "started": "2026-10-14 18:00",
            "model": "haiku",
            "session": "9c3d…e12",
            "minutes": 20,
            "tokens": 300_000,
        }
    )
    assert run.started == datetime(2026, 10, 14, 18, 0)
    assert run.task == "all"

    review = Review.model_validate({"verdict": "changes", "comment": "Add the install section."})
    assert review.verdict == "changes"
    with pytest.raises(ValidationError):
        Review.model_validate({"verdict": "maybe"})


def test_repo_spec_matches_vault_step() -> None:
    step = Step.model_validate(frontmatter.load(DEMO / "steps" / "102.md").metadata)
    spec = VAULT / "demo-repo" / "sprint" / f"{step.step}-api.md"
    assert spec.read_text().splitlines()[0] == f"# Step {step.step} — {step.title}"


def test_progress_lines_parse_into_tasks() -> None:
    text = (VAULT / "demo-repo" / "sprint" / "progress" / "102.md").read_text()
    tasks = [
        Task(state=m["mark"], text=m["text"])
        for m in re.finditer(r"^- \[(?P<mark>[ ~x])\] (?P<text>.+)$", text, re.M)
    ]
    assert [t.state for t in tasks] == [TaskState.done, TaskState.doing, TaskState.todo]
    assert tasks[1].text == "Serve `/health`"
