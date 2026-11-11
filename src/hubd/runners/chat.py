"""A live Claude chat through the headless mode: `claude -p`, stream-json (ROADMAP rule 4)."""

import json
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Protocol

log = logging.getLogger(__name__)

# Called for every hubd chat event: (chat_id, event). Event types: text, tool, tool_result,
# turn_end, error. The page gets them as they are (603).
ChatEvent = Callable[[str, dict[str, Any]], Awaitable[None]]

SHORT = 80  # characters kept of a tool input or result


class ChatRunner(Protocol):
    """Every call returns at once; what Claude says comes later, through `ChatEvent`."""

    async def open(self, chat_id: str, cwd: Path, model: str, effort: str | None) -> None:
        """Start the chat in `cwd`, or resume it when `chat_id` was opened before."""
        ...

    async def send(self, chat_id: str, text: str) -> None: ...

    async def stop(self, chat_id: str) -> None:
        """End the claude process. `open` with the same id resumes the chat."""
        ...

    async def close(self, chat_id: str) -> None:
        """Stop, and forget the chat."""
        ...


def _short(value: Any) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    text = " ".join(text.split())
    return text if len(text) <= SHORT else text[: SHORT - 1] + "…"


def _tool_input(given: Any) -> str:
    """The first string field (command, file_path, pattern…), else the whole input."""
    if isinstance(given, dict):
        for value in given.values():
            if isinstance(value, str):
                return _short(value)
    return _short(given)


def _result_text(content: Any) -> str:
    if isinstance(content, list):
        content = " ".join(b.get("text", "") for b in content if isinstance(b, dict))
    return _short(content or "")


class Parser:
    """stdout line of `claude -p --output-format stream-json` -> hubd events. Never raises."""

    # Message types documented in the Agent SDK `SDKMessage` union that carry nothing hubd shows
    # yet. https://code.claude.com/docs/en/agent-sdk/typescript (checked 2026-11-11)
    QUIET = {"system", "rate_limit_event", "prompt_suggestion"}

    def __init__(self) -> None:
        self.unknown: set[str] = set()  # types logged once already

    def events(self, line: str) -> list[dict[str, Any]]:
        try:
            message = json.loads(line)
            kind = message["type"]
            return getattr(self, f"_{kind}", self._other)(message)
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            if line.strip():
                log.warning("chat: skipped a bad stdout line (%s): %.200s", exc, line)
            return []

    def _other(self, message: dict) -> list[dict[str, Any]]:
        kind = message["type"]
        if kind not in self.QUIET and kind not in self.unknown:
            self.unknown.add(kind)
            log.warning("chat: skipped unknown stream-json type %r", kind)
        return []

    # Text arrives as deltas; the full `assistant` message that follows repeats it.
    # https://code.claude.com/docs/en/agent-sdk/streaming-output (checked 2026-11-11)
    def _stream_event(self, message: dict) -> list[dict[str, Any]]:
        delta = message["event"].get("delta") or {}
        if delta.get("type") == "text_delta" and message.get("parent_tool_use_id") is None:
            return [{"type": "text", "text": delta["text"]}]
        return []

    def _assistant(self, message: dict) -> list[dict[str, Any]]:
        return [
            {
                "type": "tool",
                "id": block.get("id"),
                "name": block["name"],
                "input": _tool_input(block.get("input")),
            }
            for block in message["message"]["content"]
            if block.get("type") == "tool_use"
        ]

    def _user(self, message: dict) -> list[dict[str, Any]]:
        content = message["message"]["content"]
        if not isinstance(content, list):
            return []  # a replayed user prompt
        return [
            {
                "type": "tool_result",
                "id": block.get("tool_use_id"),
                "error": bool(block.get("is_error")),
                "text": _result_text(block.get("content")),
            }
            for block in content
            if isinstance(block, dict) and block.get("type") == "tool_result"
        ]

    def _result(self, message: dict) -> list[dict[str, Any]]:
        usage = message.get("usage") or {}
        end = {
            "type": "turn_end",
            "cost_usd": message.get("total_cost_usd"),
            # Most of the prompt is cached: `input_tokens` alone is a handful.
            "input_tokens": sum(
                usage.get(k) or 0
                for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
            ),
            "output_tokens": usage.get("output_tokens"),
            "duration_ms": message.get("duration_ms"),
        }
        if not message.get("is_error"):
            return [end]
        why = "; ".join(message.get("errors") or []) or message.get("result") or message["subtype"]
        return [{"type": "error", "message": str(why)}, end]
