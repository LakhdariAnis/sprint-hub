"""The permission prompt tool of a chat: a stdio MCP server `claude` starts (607).

`python -m hubd.runners.permit SOCKET`: each `tools/call` goes to hubd on the chat's unix socket
as one JSON line, and hubd's answer line goes back to Claude as the tool's one text block.

The tool gets `{"tool_name", "input", "tool_use_id"}` (seen in a real run, 2.1.299: the docs do not
list it) and returns `{"behavior": "allow"}` or `{"behavior": "deny", "message": …}` as text, with
no `structuredContent`. https://code.claude.com/docs/en/errors#permission-prompt-tool-returned-an-invalid-result
and https://code.claude.com/docs/en/cli-reference (`--permission-prompt-tool`), checked 2026-11-11.
"""

import json
import socket
import sys
from typing import Any

SERVER = "sprint_hub"
TOOL = "permit"
NAME = f"mcp__{SERVER}__{TOOL}"  # what `--permission-prompt-tool` takes
SCHEMA = {
    "type": "object",
    "properties": {
        "tool_name": {"type": "string"},
        "input": {"type": "object"},
        "tool_use_id": {"type": "string"},
    },
    "required": ["tool_name", "input"],
}


def ask_hubd(path: str, arguments: dict[str, Any]) -> str:
    try:
        with socket.socket(socket.AF_UNIX) as sock:
            sock.connect(path)
            sock.sendall(json.dumps(arguments).encode() + b"\n")
            answer = sock.makefile("rb").readline()  # hubd waits for Anis, then times out
        json.loads(answer)
        return answer.decode().strip()
    except (OSError, ValueError) as exc:
        return json.dumps({"behavior": "deny", "message": f"hubd did not answer: {exc}"})


def result(path: str, message: dict[str, Any]) -> dict[str, Any] | None:
    method, params = message.get("method"), message.get("params") or {}
    if method == "initialize":
        return {
            "protocolVersion": params.get("protocolVersion", "2025-06-18"),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER, "version": "1"},
        }
    if method == "tools/list":
        about = "Asks Anis in sprint-hub whether a tool call may run."
        return {"tools": [{"name": TOOL, "description": about, "inputSchema": SCHEMA}]}
    if method == "tools/call":
        text = ask_hubd(path, params.get("arguments") or {})
        return {"content": [{"type": "text", "text": text}]}
    return {}  # ping and the rest: nothing to say


def main(path: str) -> None:
    # shortcut: one call at a time, so parallel tool calls get their cards one after the other
    # and a ping waits behind an open card. Upgrade if Claude Code starts timing out on that.
    for line in sys.stdin:
        try:
            message = json.loads(line)
        except ValueError:
            continue
        if "id" not in message:  # a notification: no answer
            continue
        reply = {"jsonrpc": "2.0", "id": message["id"], "result": result(path, message)}
        sys.stdout.write(json.dumps(reply) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main(sys.argv[1])
