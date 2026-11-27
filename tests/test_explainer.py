import re

import pytest

from hubd.explainer import SECTIONS, STAGES, TYPE_LINE, prompt


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
