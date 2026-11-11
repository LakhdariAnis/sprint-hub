"""Chats the page opened: meta and turns in memory (609 rebuilds them from the vault)."""

import asyncio
import time
import uuid
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from hubd.daemon import NotFound
from hubd.runners.chat import ChatEvent, ChatRunner

MAX_LIVE = 3  # claude processes at once
IDLE = 15 * 60  # seconds without a message or an event before the process is closed
EVERY = 60  # seconds between idle checks


class Full(Exception):
    """A 4th live chat process, or a change while Claude answers: the page shows why (409)."""


@dataclass
class Chat:
    id: str
    project: str | None
    model: str
    effort: str
    cwd: Path
    used: float = field(default_factory=time.monotonic)  # last message or event
    # One turn = the message sent and the events it got (as `chat` events, text deltas joined).
    # `done`: it ended.
    turns: list[dict[str, Any]] = field(default_factory=list)

    @property
    def busy(self) -> bool:
        return any(not t["done"] for t in self.turns)


class Chats:
    def __init__(self, runner: Callable[[ChatEvent], ChatRunner], emit: Callable[[dict], None]):
        self.runner = runner(self.on_event)
        self.emit = emit
        self.chats: dict[str, Chat] = {}

    def get(self, chat_id: str) -> Chat:
        if chat_id not in self.chats:
            raise NotFound(f"no chat {chat_id}")
        return self.chats[chat_id]

    def live(self, chat_id: str) -> bool:
        return chat_id in self.runner.chats

    def _room(self, chat_id: str | None = None) -> None:
        live = list(self.runner.chats)
        if chat_id not in live and len(live) >= MAX_LIVE:
            names = ", ".join(live)
            raise Full(f"{MAX_LIVE} chats are open already ({names}): stop one first")

    async def open(self, project: str | None, cwd: Path, model: str, effort: str) -> Chat:
        self._room()
        chat = Chat(str(uuid.uuid4()), project, model, effort, cwd)
        self.chats[chat.id] = chat
        await self.runner.open(chat.id, cwd, model, effort)
        return chat

    async def send(self, chat_id: str, text: str) -> None:
        chat = self.get(chat_id)
        chat.used = time.monotonic()
        if not self.live(chat_id):
            self._room(chat_id)
            await self.runner.open(chat.id, chat.cwd, chat.model, chat.effort)  # resumes it
        chat.turns.append({"text": text, "events": [], "done": False})
        await self.runner.send(chat_id, text)

    async def update(self, chat_id: str, model: str | None, effort: str | None) -> Chat:
        """New model or effort: a live process is closed and resumed with the new flag."""
        chat = self.get(chat_id)
        if chat.busy:  # closing now would cut the answer
            raise Full("Claude is answering: change model or effort when it is done")
        chat.model, chat.effort = model or chat.model, effort or chat.effort
        if self.live(chat_id):
            await self.runner.stop(chat_id)
            await self.runner.open(chat_id, chat.cwd, chat.model, chat.effort)  # resumes it
        return chat

    async def stop(self, chat_id: str) -> None:
        """End the process, mid-turn or not. The next message resumes the chat."""
        chat = self.get(chat_id)
        await self.runner.stop(chat_id)
        if chat.busy:  # the turn got no `turn_end`
            await self.on_event(chat_id, {"type": "stopped"})

    async def on_event(self, chat_id: str, event: dict[str, Any]) -> None:
        kind, rest = event["type"], {k: v for k, v in event.items() if k != "type"}
        if "id" in rest:  # a tool call's id: `id` is the chat's in a `chat` event
            rest["tool_id"] = rest.pop("id")
        event = {"kind": kind, **rest}  # kept as the page gets it, less the chat id
        chat = self.chats.get(chat_id)
        if chat:
            chat.used = time.monotonic()
        waiting = [t for t in chat.turns if not t["done"]] if chat else []
        if waiting:  # a message sent mid-turn waits: events go to the oldest turn not ended
            events = waiting[0]["events"]
            if kind == "text" and events and events[-1]["kind"] == "text":
                events[-1] = {**events[-1], "text": events[-1]["text"] + event["text"]}
            else:
                events.append(event)
            waiting[0]["done"] = kind == "turn_end"
        if kind == "stopped" or (kind == "error" and not self.live(chat_id)):
            for turn in waiting:  # the process is gone: no `turn_end` comes
                turn["done"] = True
        self.emit({"type": "chat", "id": chat_id, **event})

    async def close_idle(self, now: float, idle: float = IDLE) -> None:
        """Close the process of each chat with no turn under way and nothing for `idle` s."""
        for chat in list(self.chats.values()):
            if self.live(chat.id) and not chat.busy and now - chat.used >= idle:
                await self.runner.stop(chat.id)
                self.emit({"type": "chat", "id": chat.id, "kind": "closed"})

    async def loop(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            await self.close_idle(time.monotonic())
            with suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), EVERY)

    async def close_all(self) -> None:
        """hubd shuts down: no claude process outlives it. Nothing resumes them on start."""
        await asyncio.gather(*(self.runner.close(i) for i in list(self.runner.chats)))

    def json(self, chat: Chat) -> dict:
        return {
            "id": chat.id,
            "project": chat.project,
            "model": chat.model,
            "effort": chat.effort,
            "cwd": str(chat.cwd),
            "live": self.live(chat.id),
            "busy": chat.busy,
            "turns": chat.turns,
        }
