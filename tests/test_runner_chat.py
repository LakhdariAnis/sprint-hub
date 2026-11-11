"""ChatRunner: the stream-json parser and the claude -p process, without Claude."""

import json
import logging

import pytest

from hubd.runners.chat import Parser

S = '"session_id":"d5fdb32b-559f-4e47-8b49-a1c841579a7f"'


def delta(text: str, parent: str = "null") -> str:
    return (
        '{"type":"stream_event","event":{"type":"content_block_delta","index":1,'
        f'"delta":{{"type":"text_delta","text":{json.dumps(text)}}}}},{S},'
        f'"parent_tool_use_id":{parent}}}'
    )


# Shapes from a real run of claude 2.1.299 (haiku, `ls` then "hi"), trimmed.
INIT = f'{{"type":"system","subtype":"init","cwd":"/tmp/x",{S},"tools":["Bash","Read"]}}'
TOOL_DELTA = (
    '{"type":"stream_event","event":{"type":"content_block_delta","index":0,'
    f'"delta":{{"type":"input_json_delta","partial_json":"{{\\"comm"}}}},{S}}}'
)
TOOL = (
    '{"type":"assistant","message":{"model":"claude-haiku-5-5","role":"assistant","content":'
    '[{"type":"tool_use","id":"toolu_01","name":"Bash","input":{"command":"ls",'
    f'"description":"List files in current directory"}}}}]}},"parent_tool_use_id":null,{S}}}'
)
TOOL_RESULT = (
    '{"type":"user","message":{"role":"user","content":[{"tool_use_id":"toolu_01",'
    '"type":"tool_result","content":"(Bash completed with no output)","is_error":false}]},'
    f'"parent_tool_use_id":null,{S}}}'
)
TEXT_DONE = (
    '{"type":"assistant","message":{"role":"assistant","content":'
    f'[{{"type":"text","text":"The folder is empty."}}]}},"parent_tool_use_id":null,{S}}}'
)
RESULT = (
    '{"type":"result","subtype":"success","is_error":false,"duration_ms":4120,'
    '"total_cost_usd":0.00388972,"usage":{"input_tokens":4,"cache_creation_input_tokens":17015,'
    f'"cache_read_input_tokens":31832,"output_tokens":336}},"result":"Hi",{S}}}'
)
RATE = f'{{"type":"rate_limit_event","rate_limit_info":{{"status":"allowed"}},{S}}}'


def test_text_deltas_come_one_by_one() -> None:
    parser = Parser()
    assert parser.events(delta("The")) == [{"type": "text", "text": "The"}]
    assert parser.events(delta(" folder")) == [{"type": "text", "text": " folder"}]
    assert parser.events(TEXT_DONE) == []  # already streamed


def test_a_subagent_text_is_not_the_answer() -> None:
    assert Parser().events(delta("inside", parent='"toolu_01"')) == []


def test_tool_call_and_its_result() -> None:
    parser = Parser()
    assert parser.events(TOOL_DELTA) == []
    assert parser.events(TOOL) == [
        {"type": "tool", "id": "toolu_01", "name": "Bash", "input": "ls"}
    ]
    assert parser.events(TOOL_RESULT) == [
        {
            "type": "tool_result",
            "id": "toolu_01",
            "error": False,
            "text": "(Bash completed with no output)",
        }
    ]


def test_long_tool_input_is_cut() -> None:
    line = TOOL.replace('"command":"ls"', '"command":"' + "x" * 200 + '"')
    (tool,) = Parser().events(line)
    assert len(tool["input"]) == 80 and tool["input"].endswith("…")


def test_result_ends_the_turn() -> None:
    assert Parser().events(RESULT) == [
        {
            "type": "turn_end",
            "cost_usd": 0.00388972,
            "input_tokens": 4 + 17015 + 31832,
            "output_tokens": 336,
            "duration_ms": 4120,
        }
    ]


def test_error_result_says_why_and_still_ends_the_turn() -> None:
    line = RESULT.replace(
        '"subtype":"success","is_error":false',
        ('"subtype":"error_during_execution","is_error":true,"errors":["API Error: 500"]'),
    )
    error, end = Parser().events(line)
    assert error == {"type": "error", "message": "API Error: 500"}
    assert end["type"] == "turn_end"


@pytest.mark.parametrize("line", ["not json", "[1,2]", '{"no":"type"}', '{"type":"user"}', ""])
def test_junk_line_is_skipped(line: str) -> None:
    assert Parser().events(line) == []


def test_unknown_type_is_logged_once(caplog: pytest.LogCaptureFixture) -> None:
    parser = Parser()
    with caplog.at_level(logging.WARNING):
        assert parser.events('{"type":"brand_new"}') == []
        assert parser.events('{"type":"brand_new","x":1}') == []
        assert parser.events(INIT) == parser.events(RATE) == []
    assert [r.getMessage() for r in caplog.records] == [
        "chat: skipped unknown stream-json type 'brand_new'"
    ]
