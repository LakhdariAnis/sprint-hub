"""Contract: the parser maps real `claude -p` stdout, one sample per Claude Code version."""

import json
from pathlib import Path

import pytest

from hubd.runners.chat import Parser

SAMPLES = sorted((Path(__file__).parent / "fixtures" / "claude-stream-json").glob("claude-*.jsonl"))
LINES = [(s.name, n, line) for s in SAMPLES for n, line in enumerate(s.read_text().splitlines(), 1)]


def test_there_is_a_sample() -> None:
    assert SAMPLES


@pytest.mark.parametrize("name,number,line", LINES, ids=[f"{n}:{i}" for n, i, _ in LINES])
def test_every_line_is_a_json_message_with_a_type(name: str, number: int, line: str) -> None:
    assert isinstance(json.loads(line)["type"], str)


@pytest.mark.parametrize("sample", SAMPLES, ids=lambda s: s.name)
def test_sample_maps_to_text_a_tool_call_and_its_result_then_the_turn_end(sample: Path) -> None:
    parser = Parser()
    events = [e for line in sample.read_text().splitlines() for e in parser.events(line)]
    kinds = [e["type"] for e in events]
    # The prompt of make-sample.sh: "Run ls, then say hi in one word." The words differ per run.
    assert kinds[:2] == ["tool", "tool_result"]
    assert set(kinds[2:-1]) == {"text"}
    assert kinds[-1] == "turn_end" and kinds.count("turn_end") == 1
    tool, result, *_, end = events
    assert tool["name"] == "Bash" and tool["input"].startswith("ls")
    assert result["id"] == tool["id"] and not result["error"] and "notes.txt" in result["text"]
    assert "".join(e["text"] for e in events if e["type"] == "text").strip()
    assert end["cost_usd"] > 0 and end["output_tokens"] > 0 and end["input_tokens"] > 0
    assert end["duration_ms"] > 0
    assert parser.unknown == set()  # a new message type from Claude Code shows here first
