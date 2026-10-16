from datetime import datetime
from pathlib import Path

import frontmatter
import pytest

from hubd.model import Review, Run, State, TaskState
from hubd.vault import (
    FileError,
    _load_step,
    load_vault,
    parse_body,
    parse_run,
    save_step,
    split_sections,
)

VAULT = Path(__file__).parent / "fixtures" / "vault"
STEPS = VAULT / "projects" / "demo" / "steps"


def test_split_sections() -> None:
    body = "intro\n## Runs\n- a\n\n## Review\nverdict:\n"
    assert split_sections(body) == {"Runs": ["- a", ""], "Review": ["verdict:"]}


def test_parse_run_all_fields() -> None:
    run = parse_run(
        "- 2026-10-15 22:10 · sonnet · session 7b1e…a04 · 42 min · 1.2M tokens · task all"
    )
    assert run == Run(
        started=datetime(2026, 10, 15, 22, 10),
        model="sonnet",
        session="7b1e…a04",
        minutes=42,
        tokens=1_200_000,
        task="all",
    )


def test_parse_run_rejects_unknown_field() -> None:
    with pytest.raises(ValueError, match="unknown run field"):
        parse_run("- 2026-10-15 22:10 · sonnet · session x · 3 apples")


def test_body_without_runs_or_verdict() -> None:
    runs, review = parse_body(frontmatter.load(STEPS / "101.md").content)
    assert runs == []
    assert review == Review()


def test_body_with_run_and_review() -> None:
    runs, review = parse_body(frontmatter.load(STEPS / "104.md").content)
    assert [(r.model, r.minutes, r.tokens) for r in runs] == [("haiku", 20, 300_000)]
    assert review == Review(verdict="changes", comment="Add the install section.")


def test_body_without_review_section() -> None:
    assert parse_body("## Runs\n") == ([], None)


def test_load_vault_good_fixtures() -> None:
    index = load_vault(VAULT)
    assert list(index.projects) == ["broken", "demo"]
    assert [(e.project, e.step.step) for e in index.steps] == [
        ("demo", "101"),
        ("demo", "102"),
        ("demo", "103"),
        ("demo", "104"),
        ("demo", "105"),
    ]
    assert [e.step.state for e in index.steps] == list(State)
    assert index.steps[3].step.review == Review(
        verdict="changes", comment="Add the install section."
    )


def test_step_joined_with_spec_and_checklist() -> None:
    entries = {e.step.step: e for e in load_vault(VAULT).steps}
    doing = entries["102"]
    assert doing.spec == VAULT / "demo-repo" / "sprint" / "102-api.md"
    assert [t.state for t in doing.tasks] == [TaskState.done, TaskState.doing, TaskState.todo]
    assert (entries["101"].spec, entries["101"].tasks) == (None, [])


def test_step_id_keeps_leading_zero(tmp_path: Path) -> None:
    steps = tmp_path / "projects" / "p" / "steps"
    steps.mkdir(parents=True)
    (tmp_path / "projects" / "p" / "project.md").write_text(
        "---\nname: p\nmodel: sonnet\nmerge: auto\n---\n"
    )
    (steps / "02.md").write_text("---\nstep: 02\ntitle: x\nstate: todo\n---\n")
    index = load_vault(tmp_path)
    assert index.errors == []
    assert index.steps[0].step.step == "02"


def test_each_broken_file_gives_one_error() -> None:
    steps = VAULT / "projects" / "broken" / "steps"
    assert load_vault(VAULT).errors == [
        FileError(steps / "201.md", 3, "bad YAML: mapping values are not allowed in this context"),
        FileError(
            steps / "202.md",
            4,
            "state: Input should be 'todo', 'doing', 'done', 'changes' or 'approved'",
        ),
        FileError(steps / "203.md", None, "title: Field required"),
    ]


def test_missing_project_file_is_an_error(tmp_path: Path) -> None:
    (tmp_path / "projects" / "p").mkdir(parents=True)
    [error] = load_vault(tmp_path).errors
    assert error.path == tmp_path / "projects" / "p" / "project.md"


def _copy_step(tmp_path: Path, name: str) -> Path:
    path = tmp_path / f"{name}.md"
    path.write_bytes((STEPS / f"{name}.md").read_bytes())
    return path


@pytest.mark.parametrize("name", ["101", "102", "103", "104", "105"])
def test_save_unchanged_is_byte_identical(tmp_path: Path, name: str) -> None:
    path = _copy_step(tmp_path, name)
    before = path.read_bytes()
    save_step(path, _load_step(path))
    assert path.read_bytes() == before


def test_save_state_changes_only_that_line(tmp_path: Path) -> None:
    path = _copy_step(tmp_path, "102")
    before = path.read_text().splitlines()
    step = _load_step(path)
    step.state = State.done
    save_step(path, step)
    after = path.read_text().splitlines()
    assert [(a, b) for a, b in zip(before, after, strict=True) if a != b] == [
        (
            "state: doing   # todo | doing | done | changes | approved",
            "state: done   # todo | doing | done | changes | approved",
        )
    ]
    assert _load_step(path).state is State.done


def test_save_adds_and_removes_fields(tmp_path: Path) -> None:
    path = _copy_step(tmp_path, "101")
    step = _load_step(path)
    step.branch = "step/101-repo"
    step.needs = ["100", "99"]
    save_step(path, step)
    assert "branch: step/101-repo\nneeds: [100, 99]\n---\n" in path.read_text()
    step.branch = None
    save_step(path, step)
    assert "branch:" not in path.read_text()
    assert _load_step(path).needs == ["100", "99"]
