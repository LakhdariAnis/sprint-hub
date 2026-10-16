from datetime import datetime
from pathlib import Path

import frontmatter
import pytest

from hubd.model import Review, Run
from hubd.vault import parse_body, parse_run, split_sections

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
