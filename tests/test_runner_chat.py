"""ChatRunner: the stream-json parser and the claude -p process, without Claude."""

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

import pytest

from hubd.runners import permit
from hubd.runners.chat import ClaudeChat, Parser

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


def test_turn_cost_is_its_share_of_the_running_total() -> None:
    parser = Parser()
    parser.events(RESULT)
    (end,) = parser.events(RESULT.replace("0.00388972", "0.01"))
    assert end["cost_usd"] == 0.00611028


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


# A stand-in for `claude`: writes its argv, echoes each message as two deltas and a result.
# "die" exits 3 after a stderr line; "hang" ignores stdin EOF; "ask <tool>" calls the permission
# prompt tool from `--mcp-config` as Claude does and says its answer.
STUB = f"""#!{sys.executable}
import json, signal, subprocess, sys, time
args = sys.argv[1:]
open(sys.argv[0] + ".args", "w").write(json.dumps(args))
for line in sys.stdin:
    text = json.loads(line)["message"]["content"]
    if text.startswith("ask "):
        server = json.loads(args[args.index("--mcp-config") + 1])["mcpServers"]["sprint_hub"]
        call = {{"tool_name": text[4:], "input": {{"command": "ls"}}, "tool_use_id": "t1"}}
        calls = [{{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {{}}}},
            {{"jsonrpc": "2.0", "method": "notifications/initialized"}},
            {{"jsonrpc": "2.0", "id": 2, "method": "tools/call",
              "params": {{"name": "permit", "arguments": call}}}}]
        rpc = "".join(json.dumps(c) + "\\n" for c in calls)
        out = subprocess.run([server["command"], *server["args"]], input=rpc, text=True,
            capture_output=True).stdout.splitlines()
        text = json.loads(out[-1])["result"]["content"][0]["text"]
    if text == "die":
        print("boom", file=sys.stderr, flush=True)
        sys.exit(3)
    if text == "hang":
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
        time.sleep(60)
    for piece in ("you said ", text):
        delta = {{"type": "text_delta", "text": piece}}
        print(json.dumps({{"type": "stream_event", "parent_tool_use_id": None,
            "event": {{"type": "content_block_delta", "delta": delta}}}}))
    print("junk")
    print(json.dumps({{"type": "result", "subtype": "success", "is_error": False,
        "duration_ms": 5, "total_cost_usd": 0.01, "usage": {{"output_tokens": 2}}}}), flush=True)
"""
ID = "8f6a0c2e-3b1d-4c5e-9f7a-1b2c3d4e5f60"


@pytest.fixture
def stub(tmp_path: Path) -> Path:
    path = tmp_path / "claude"
    path.write_text(STUB)
    path.chmod(0o755)
    return path


def runner(stub: Path) -> tuple[ClaudeChat, asyncio.Queue[tuple[str, dict[str, Any]]]]:
    events: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue()

    async def on_event(chat_id: str, event: dict[str, Any]) -> None:
        await events.put((chat_id, event))

    return ClaudeChat(on_event, claude=str(stub), projects=stub.parent / "projects"), events


async def until(events: asyncio.Queue, kind: str) -> list[dict[str, Any]]:
    """Events up to and with the first of type `kind`."""
    seen = []
    while not seen or seen[-1]["type"] != kind:
        chat_id, event = await asyncio.wait_for(events.get(), 5)
        assert chat_id == ID
        seen.append(event)
    return seen


def test_chat_streams_the_answer_and_stops_quietly(stub: Path) -> None:
    async def main() -> None:
        chat, events = runner(stub)
        await chat.open(ID, stub.parent, "haiku", "low")
        await chat.send(ID, "hi")
        seen = await until(events, "turn_end")
        assert [e.get("text") for e in seen[:2]] == ["you said ", "hi"]
        assert seen[2]["cost_usd"] == 0.01
        await chat.send(ID, "again")
        assert (await until(events, "turn_end"))[1]["text"] == "again"
        await chat.stop(ID)
        assert events.empty() and ID not in chat.chats

    asyncio.run(main())
    args = json.loads(Path(f"{stub}.args").read_text())
    assert args[:7] == [
        "--print",
        "--input-format",
        "stream-json",
        "--output-format",
        "stream-json",
        "--verbose",
        "--include-partial-messages",
    ]
    config = json.loads(args[12])
    socket = config["mcpServers"]["sprint_hub"]["args"][-1]
    assert args[7:12] == [
        "--permission-mode",
        "default",
        "--permission-prompts",
        "host",
        "--mcp-config",
    ]
    assert config == {
        "mcpServers": {
            "sprint_hub": {"command": sys.executable, "args": ["-m", "hubd.runners.permit", socket]}
        }
    }
    assert not Path(socket).parent.exists()  # removed when claude ended
    assert args[13:] == [
        "--permission-prompt-tool",
        "mcp__sprint_hub__permit",
        "--model",
        "haiku",
        "--effort",
        "low",
        "--session-id",
        ID,
    ]


def test_known_chat_is_resumed(stub: Path) -> None:
    (stub.parent / "projects" / "-tmp-x").mkdir(parents=True)
    (stub.parent / "projects" / "-tmp-x" / f"{ID}.jsonl").touch()
    chat, _ = runner(stub)
    assert chat.args(ID, "opus", None)[-4:] == ["--model", "opus", "--resume", ID]
    told = chat.args(ID, "opus", "low", "# context")[-6:]
    assert told == ["--effort", "low", "--append-system-prompt", "# context", "--resume", ID]


def test_bad_exit_is_an_error_with_stderr(stub: Path) -> None:
    async def main() -> None:
        chat, events = runner(stub)
        await chat.open(ID, stub.parent, "haiku", None)
        await chat.send(ID, "die")
        (error,) = await until(events, "error")
        assert error["message"] == "claude exited with code 3:\nboom"
        assert ID not in chat.chats
        await chat.send(ID, "hi")
        assert (await until(events, "error"))[0]["message"] == "chat is not open"

    asyncio.run(main())


def test_stop_terminates_a_claude_that_hangs(stub: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("hubd.runners.chat.STOP_WAIT", 0.2)

    async def main() -> None:
        chat, events = runner(stub)
        await chat.open(ID, stub.parent, "haiku", None)
        await chat.send(ID, "hang")
        await chat.close(ID)
        assert events.empty()

    asyncio.run(main())


def test_missing_claude_is_an_error(tmp_path: Path) -> None:
    async def main() -> None:
        chat, events = runner(tmp_path / "nope")
        await chat.open(ID, tmp_path, "haiku", None)
        (error,) = await until(events, "error")
        assert error["message"].startswith("claude did not start")

    asyncio.run(main())


def test_permission_prompt_reaches_ask_and_its_answer_goes_back(stub: Path) -> None:
    asked: list[tuple[str, str, dict]] = []

    async def ask(chat_id: str, tool: str, given: dict) -> dict[str, str]:
        asked.append((chat_id, tool, given))
        return {"behavior": "deny", "message": "Anis denied"}

    async def main() -> None:
        chat, events = runner(stub)
        chat.ask = ask
        await chat.open(ID, stub.parent, "haiku", None, scratch=True)
        await chat.send(ID, "ask Bash")
        seen = await until(events, "turn_end")
        assert json.loads(seen[1]["text"]) == {"behavior": "deny", "message": "Anis denied"}
        await chat.stop(ID)

    asyncio.run(main())
    assert asked == [(ID, "Bash", {"command": "ls"})]
    args = json.loads(Path(f"{stub}.args").read_text())
    assert args[7:11] == ["--permission-mode", "default", "--disallowedTools", "Bash,PowerShell"]


def test_permit_server_denies_when_hubd_is_gone(tmp_path: Path) -> None:

    answer = json.loads(permit.ask_hubd(str(tmp_path / "none.sock"), {"tool_name": "Bash"}))
    assert answer["behavior"] == "deny" and "hubd did not answer" in answer["message"]
    assert permit.result("x", {"method": "tools/list"})["tools"][0]["name"] == "permit"
