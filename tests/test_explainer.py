import re
from datetime import UTC, datetime
from pathlib import Path

import frontmatter
import pytest

from hubd.explainer import SECTIONS, STAGES, TYPE_LINE, Page, blocks, page, problems, prompt, write
from hubd.runners.fake import EXPLAINER


@pytest.mark.parametrize("kind", list(STAGES))
def test_prompt_has_the_nine_headings_in_order_and_the_type_stages(kind: str) -> None:
    text = prompt("tinyml", kind)
    numbered = re.findall(r"(?m)^\d\. (.+)$", text)
    assert numbered == list(SECTIONS) and len(numbered) == 9
    assert " → ".join(STAGES[kind]) in text
    others = [k for k in STAGES if k != kind]
    assert all(" → ".join(STAGES[k]) not in text for k in others)
    assert TYPE_LINE not in text


def test_prompt_without_type_lists_every_type_and_asks_to_say_which() -> None:
    text = prompt("tinyml", None)
    assert all(" → ".join(s) in text for s in STAGES.values())
    assert f"`{TYPE_LINE}<type>`" in text


def test_prompt_keeps_numbers_real_and_names_as_code() -> None:
    text = prompt("tinyml", "ml")
    assert "never invent" in text and "inline code" in text
    assert all(f"```{b}" in text for b in ("stages", "kpis", "bars"))


def test_the_fake_explainer_parses_with_no_problems() -> None:
    assert problems(EXPLAINER) == []
    found = blocks(EXPLAINER)
    assert [r[0] for r in found["stages"]] == list(STAGES["app"])
    assert found["kpis"][0] == ["2", "screens"] and found["bars"][1] == ["routes", "1"]


def test_problems_names_what_is_off() -> None:
    text = "## In one sentence\n\n```stages\na | b\n```\n\n```bars\nx | 3 KB\n```\n"
    found = problems(text)
    assert any("headings" in p for p in found)
    assert "stages: a | b has not 5 cells" in found
    assert "no ```kpis block" in found and "bars: 3 KB is not a plain number" in found


def test_page_reads_the_guessed_type_and_drops_preamble() -> None:
    p = page(EXPLAINER, None)
    assert (p.kind, p.guessed) == ("app", True) and p.body.startswith("## In one sentence")
    assert page("type: spaceship\n## In one sentence", None).kind is None
    assert page("Here it is:\n## In one sentence", "ml") == Page("ml", False, "## In one sentence")


def test_write_lands_next_to_project_md_with_frontmatter(tmp_path: Path) -> None:
    (tmp_path / "project.md").write_text("---\nname: demo\n---\n")
    path = write(
        tmp_path, page(EXPLAINER, "app"), "2026-11-27T10:00:00+00:00", "0123456", "opus", 0.42
    )
    assert path == tmp_path / "explainer.md"
    doc = frontmatter.load(path)
    assert doc.metadata == {
        "written": datetime(2026, 11, 27, 10, tzinfo=UTC),
        "commit": "0123456",
        "model": "opus",
        "type": "app",
        "cost": 0.42,
    }
    assert doc.content.startswith("## In one sentence") and problems(doc.content) == []


def test_a_guessed_type_says_so_in_the_file(tmp_path: Path) -> None:
    doc = frontmatter.load(write(tmp_path, page(EXPLAINER, None), "t", None, None, None))
    assert doc.metadata["guessed"] is True and doc.metadata["type"] == "app"
    assert doc.content.startswith("> Type guessed by Claude: app.")
