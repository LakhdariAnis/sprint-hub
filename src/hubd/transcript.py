"""Turns of a chat read back from Claude's session file, for a chat hubd restarted.

The file is not documented (ROADMAP rule 4): this is nice-to-have only. Anything it does not
understand is skipped, and a file it cannot use gives None; the chat still resumes without them.
"""

import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from hubd.runners.chat import PROJECTS, _result_text, _tool_input, tool_line

log = logging.getLogger(__name__)

# chat id -> turns as `Chats` keeps them (`{"text", "events", "done"}`), or None: not readable.
Transcript = Callable[[str], list[dict[str, Any]] | None]


def no_transcript(chat_id: str) -> None:
    return None


def read_claude(chat_id: str, projects: Path = PROJECTS) -> list[dict[str, Any]] | None:
    """`~/.claude/projects/<folder>/<chat id>.jsonl`; the folder is named after the chat's cwd."""
    try:
        path = next(projects.glob(f"*/{chat_id}.jsonl"), None)
        lines = path.read_text(errors="replace").splitlines() if path else []
    except OSError as exc:
        log.warning("chat %s: session file not read (%s)", chat_id, exc)
        return None
    turns: list[dict[str, Any]] = []
    for line in lines:
        try:
            message = json.loads(line)
            if message["type"] in ("user", "assistant") and not message.get("isSidechain"):
                _take(turns, message)
        except (ValueError, KeyError, TypeError, AttributeError):
            continue  # one bad line does not lose the rest
    return turns or None


def _take(turns: list[dict[str, Any]], message: dict[str, Any]) -> None:
    role, content = message["type"], message["message"]["content"]
    cwd = Path(message["cwd"]) if isinstance(message.get("cwd"), str) else None
    blocks = [{"type": "text", "text": content}] if isinstance(content, str) else content
    for block in blocks:
        kind = block["type"]
        events = turns[-1]["events"] if turns else None
        if role == "user" and kind == "text":  # what Anis sent: a new turn
            turns.append({"text": block["text"], "events": [], "done": True})
        elif events is None or message.get("isMeta"):
            continue  # an answer with no question before it
        elif kind == "text" and role == "assistant":
            if events and events[-1]["kind"] == "text":
                events[-1]["text"] += block["text"]
            else:
                events.append({"kind": "text", "text": block["text"]})
        elif kind == "tool_use":
            given = block.get("input")
            events.append(
                {
                    "kind": "tool",
                    "tool_id": block["id"],
                    "name": block["name"],
                    "line": tool_line(block["name"], given, cwd),
                    "input": _tool_input(given),
                }
            )
        elif kind == "tool_result":
            text = _result_text(block.get("content"))
            error = bool(block.get("is_error"))
            events.append(
                {
                    "kind": "tool_result",
                    "tool_id": block["tool_use_id"],
                    "text": text,
                    "error": error,
                }
            )
