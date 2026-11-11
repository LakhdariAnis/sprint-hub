"""A live Claude chat through the headless mode: `claude -p`, stream-json (ROADMAP rule 4)."""

import asyncio
import json
import logging
import uuid
from collections import deque
from collections.abc import Awaitable, Callable, Collection
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from hubd.runners.claude import MODEL, RESUME, SESSION_ID

log = logging.getLogger(__name__)

# Every flag below is in `claude --help` (2.1.299) and https://code.claude.com/docs/en/cli-reference
# (checked 2026-11-11). Headless mode and stream-json: https://code.claude.com/docs/en/headless
# (checked 2026-11-11). `--model`, `--session-id`, `--resume` come from `claude.py`.
PRINT = "--print"  # non-interactive
INPUT_FORMAT = "--input-format"  # stream-json: one JSON user message per stdin line
OUTPUT_FORMAT = "--output-format"  # stream-json: one JSON message per stdout line
VERBOSE = "--verbose"  # the docs pair it with stream-json output
PARTIAL = "--include-partial-messages"  # text deltas as they arrive
EFFORT = "--effort"  # low, medium, high, xhigh, max
PERMISSION_MODE = "--permission-mode"  # default: reads only (help lists it as its alias `manual`)
# none: whatever would prompt is denied instead of waiting for a host. 607 answers prompts.
PERMISSION_PROMPTS = "--permission-prompts"
APPEND_SYSTEM = "--append-system-prompt"  # the project, sprint or step context (606)

STDERR_LINES = 50  # kept for the error event of a bad exit
STOP_WAIT = 5.0  # seconds claude gets to end on stdin EOF before it is terminated
LINE_LIMIT = 64 * 2**20  # a tool result can be one long stdout line; asyncio's default is 64 KiB
PROJECTS = Path.home() / ".claude" / "projects"  # where Claude keeps its transcripts

# Called for every hubd chat event: (chat_id, event). Event types: text, tool, tool_result,
# turn_end, error. The page gets them as they are (603).
ChatEvent = Callable[[str, dict[str, Any]], Awaitable[None]]

# Asked for each call Claude's permission mode would prompt for: (chat_id, tool, input) -> the
# prompt tool's answer, {"behavior": "allow"} or {"behavior": "deny", "message": …} (607).
Ask = Callable[[str, str, dict[str, Any]], Awaitable[dict[str, str]]]

SHORT = 80  # characters kept of a tool input or result


async def no_one(chat_id: str, tool: str, tool_input: dict[str, Any]) -> dict[str, str]:
    return {"behavior": "deny", "message": "Nobody can answer permission prompts here."}


class ChatRunner(Protocol):
    """Every call returns at once; what Claude says comes later, through `ChatEvent`."""

    chats: Collection[str]  # ids of the chats with a live process
    ask: Ask  # `Chats` sets it: Anis answers in the page

    async def open(
        self, chat_id: str, cwd: Path, model: str, effort: str | None, system: str | None = None
    ) -> None:
        """Start the chat in `cwd`, or resume it when `chat_id` was opened before.

        `system` is appended to Claude's system prompt; a resume needs it again.
        """
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
        self.spent = 0.0  # `total_cost_usd` so far: it adds up over the process's turns

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
        total = message.get("total_cost_usd")
        cost = None if total is None else round(total - self.spent, 8)
        self.spent = total if total is not None else self.spent
        end = {
            "type": "turn_end",
            "cost_usd": cost,  # this turn's
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


@dataclass
class _Chat:
    process: asyncio.subprocess.Process
    parser: Parser = field(default_factory=Parser)
    stderr: deque[str] = field(default_factory=lambda: deque(maxlen=STDERR_LINES))
    stopping: bool = False
    reader: asyncio.Task[None] | None = None


class ClaudeChat:
    """One `claude -p` process per open chat, stdin kept open: one stdin line per user message."""

    def __init__(
        self,
        on_event: ChatEvent,
        claude: str = "claude",
        projects: Path = PROJECTS,
    ):
        self.on_event = on_event
        self.claude = claude
        self.projects = projects
        self.chats: dict[str, _Chat] = {}

    def exists(self, chat_id: str) -> bool:
        # shortcut: Claude's transcript path is undocumented; if it moves, `--session-id` on an
        # old id fails as an `error` event. Upgrade when 609 records the chats it opened.
        return any(self.projects.glob(f"*/{chat_id}.jsonl"))

    def args(
        self, chat_id: str, model: str, effort: str | None, system: str | None = None
    ) -> list[str]:
        args = [PRINT, INPUT_FORMAT, "stream-json", OUTPUT_FORMAT, "stream-json", VERBOSE, PARTIAL]
        args += [PERMISSION_MODE, "default", PERMISSION_PROMPTS, "none", MODEL, model]
        if effort:
            args += [EFFORT, effort]
        if system:
            args += [APPEND_SYSTEM, system]
        return args + [RESUME if self.exists(chat_id) else SESSION_ID, chat_id]

    async def open(
        self, chat_id: str, cwd: Path, model: str, effort: str | None, system: str | None = None
    ) -> None:
        chat_id = str(uuid.UUID(chat_id))  # ValueError: not a session id
        if chat_id in self.chats:
            return
        try:
            process = await asyncio.create_subprocess_exec(
                self.claude,
                *self.args(chat_id, model, effort, system),
                cwd=cwd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=LINE_LIMIT,
            )
        except OSError as exc:
            await self.on_event(
                chat_id, {"type": "error", "message": f"claude did not start: {exc}"}
            )
            return
        chat = self.chats[chat_id] = _Chat(process)
        chat.reader = asyncio.create_task(self._read(chat_id, chat))

    async def send(self, chat_id: str, text: str) -> None:
        chat = self.chats.get(chat_id)
        if chat is None or chat.process.stdin is None:
            await self.on_event(chat_id, {"type": "error", "message": "chat is not open"})
            return
        message = {
            "type": "user",
            "message": {"role": "user", "content": text},
            "parent_tool_use_id": None,
        }
        try:
            chat.process.stdin.write(json.dumps(message).encode() + b"\n")
            await chat.process.stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            pass  # claude is gone: the reader reports its exit

    async def stop(self, chat_id: str) -> None:
        chat = self.chats.pop(chat_id, None)
        if chat is None:
            return
        chat.stopping = True
        process = chat.process
        if process.stdin is not None:
            process.stdin.close()  # EOF: claude ends after the turn it is in
        try:
            await asyncio.wait_for(process.wait(), STOP_WAIT)
        except TimeoutError:
            process.terminate()
            await process.wait()
        if chat.reader is not None:
            await chat.reader

    async def close(self, chat_id: str) -> None:
        await self.stop(chat_id)  # nothing else is kept per chat yet; 609 keeps the list

    async def _read(self, chat_id: str, chat: _Chat) -> None:
        process = chat.process
        assert process.stdout is not None and process.stderr is not None
        stderr = asyncio.create_task(self._tail(process.stderr, chat.stderr))
        async for raw in process.stdout:
            for event in chat.parser.events(raw.decode(errors="replace")):
                await self.on_event(chat_id, event)
        await stderr
        code = await process.wait()
        if self.chats.get(chat_id) is chat:
            del self.chats[chat_id]  # died on its own: `open` may start it again
        if code != 0 and not chat.stopping:
            tail = "\n".join(chat.stderr)
            message = f"claude exited with code {code}" + (f":\n{tail}" if tail else "")
            await self.on_event(chat_id, {"type": "error", "message": message})

    @staticmethod
    async def _tail(stream: asyncio.StreamReader, lines: deque[str]) -> None:
        async for raw in stream:
            lines.append(raw.decode(errors="replace").rstrip())


async def _try(cwd: Path, chat_id: str, model: str, effort: str | None) -> None:
    """A chat in the terminal: one line = one message, an empty line or ^D ends it."""
    turn = asyncio.Event()

    async def show(_: str, event: dict[str, Any]) -> None:
        kind = event["type"]
        if kind == "text":
            print(event["text"], end="", flush=True)
        elif kind == "turn_end":
            print(f"\n[turn_end {event}]")
            turn.set()
        else:
            print(f"\n[{kind} {event}]", flush=True)
            if kind == "error":
                turn.set()

    chat = ClaudeChat(show)
    print(f"chat {chat_id} in {cwd}")
    await chat.open(chat_id, cwd, model, effort)
    try:
        while text := await asyncio.to_thread(input, "> "):
            turn.clear()
            await chat.send(chat_id, text)
            await turn.wait()
    except EOFError:
        pass
    finally:
        await chat.close(chat_id)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=_try.__doc__)
    parser.add_argument("--try", dest="cwd", type=Path, required=True, metavar="DIR")
    parser.add_argument("--id", default=str(uuid.uuid4()), help="resume this chat")
    parser.add_argument("--model", default="sonnet")
    parser.add_argument("--effort")
    a = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(_try(a.cwd, a.id, a.model, a.effort))
