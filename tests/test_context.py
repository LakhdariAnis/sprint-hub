"""Context of a chat started from a project, a sprint or a step: files, cap, missing files."""

from pathlib import Path

import pytest

from hubd.context import CAP, build, cap

SPRINTS = """# Demo

## Sprints

| Sprint | Track | Week | Version | Goal | Planned | Actual | Status |
|---|---|---|---|---|---|---|---|
| 1 | personal | 2026-W43 | 0.2.0 | Core runs | 13 h | 5 h | closed |
| 2 | personal | 2026-W44 | 0.3.0 | Chat in the app | 13 h | | current |

## Sprint 2 — steps

| # | File | h | Result |
|---|---|---|---|
| 201 | `201-a.md` | 1 | the first |
| 202 | `202-b.md` | 1 | the second |
"""

PROGRESS = """# Progress

## 2026-11-11 — Step 202 built (branch step/202-b)

- Built: the second thing.

## 2026-11-10 — Step 201 built (branch step/201-a)

- Built: the first thing.

## 2026-10-01 — Step 105 built (branch step/105-x)

- Built: an old thing.
"""


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "sprint/progress").mkdir(parents=True)
    (tmp_path / "README.md").write_text("# Demo\n\nDemo pitch.\n" + "line\n" * 300)
    (tmp_path / "sprint/README.md").write_text(SPRINTS)
    (tmp_path / "sprint/PROGRESS.md").write_text(PROGRESS)
    (tmp_path / "sprint/progress/202.md").write_text("# Step 202\n- [x] do it\n")
    return tmp_path


def test_project(repo: Path) -> None:
    ctx = build(repo, "Demo")
    assert ctx.parts == ["README", "sprints"] and not ctx.notes
    assert "Demo pitch." in ctx.text and "| 2 | personal | 2026-W44" in ctx.text
    assert ctx.text.count("line\n") == 197  # README head: 200 lines, 3 of them the title part
    assert "Sprint 2 — steps" not in ctx.text and "Step 201" not in ctx.text


def test_sprint(repo: Path) -> None:
    ctx = build(repo, "Demo", sprint=2)
    assert ctx.parts == ["sprint 2", "steps", "progress", "README", "sprints"]
    sprint = ctx.text.split("## Project")[0]
    assert "Chat in the app" in sprint and "Core runs" not in sprint  # its row only
    assert "| 201 | `201-a.md`" in sprint
    assert "the first thing" in sprint and "the second thing" in sprint
    assert "an old thing" not in ctx.text  # a step of another sprint


def test_step(repo: Path) -> None:
    ctx = build(repo, "Demo", step="202", spec="# Step 202\n\n## Goal\nB.", diffstat=" a.py | 3 +")
    assert ctx.parts == ["spec", "checklist", "report", "diffstat", "README", "sprints"]
    step = ctx.text.split("## Project")[0]
    assert "## Goal\nB." in step and "- [x] do it" in step and " a.py | 3 +" in step
    assert "the second thing" in step and "the first thing" not in step


def test_missing_files_give_notes(tmp_path: Path) -> None:
    ctx = build(tmp_path, "Bare", sprint=1, step="101")
    assert ctx.parts == []
    assert ctx.notes == [
        "no spec for step 101",
        "no sprint/progress/101.md",
        "no sprint/PROGRESS.md",
        "no diffstat: step 101 has no branch or git failed",
        "no sprint/README.md",
        "no README.md",
    ]
    assert "[no README.md]" in ctx.text and "[no sprint/README.md]" in ctx.text


def test_sprint_not_in_table(repo: Path) -> None:
    (repo / "sprint/PROGRESS.md").unlink()
    ctx = build(repo, "Demo", sprint=9)
    assert "no row for sprint 9 in sprint/README.md" in ctx.notes
    assert "no steps table for sprint 9" in ctx.notes and "no sprint/PROGRESS.md" in ctx.notes


def test_cap_cuts_whole_lines_with_a_note() -> None:
    text = "".join(f"line {n}\n" for n in range(10_000))
    out = cap(text)
    assert len(out.encode()) <= CAP and out.endswith(" lines]")
    kept = out.split("\n")[:-1]
    assert kept == text.split("\n")[: len(kept)]
    assert out.split("\n")[-1] == f"[cut: {10_001 - len(kept)} lines]"
    assert cap("short\n") == "short\n"


def test_big_readme_is_capped(repo: Path) -> None:
    (repo / "README.md").write_text("x" * 1000 + "\n" + ("y" * 500 + "\n") * 150)
    ctx = build(repo, "Demo", step="202", spec="spec")
    assert len(ctx.text.encode()) <= CAP and "[cut: " in ctx.text
    assert "- [x] do it" in ctx.text  # the step comes first: the README tail goes
    assert ctx.json()["size"] == len(ctx.text.encode())
