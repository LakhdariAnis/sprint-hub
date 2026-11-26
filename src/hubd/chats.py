"""Chats the page opened: meta and turns in memory, the meta also in the vault (`chatlog`)."""

import asyncio
import time
import uuid
from collections.abc import Awaitable, Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from hubd import chatlog, focus, permits
from hubd.context import Context
from hubd.daemon import NotFound
from hubd.model import one_line
from hubd.notify import Click
from hubd.runners.chat import ChatEvent, ChatRunner
from hubd.transcript import Transcript, no_transcript

MAX_LIVE = 3  # claude processes at once
IDLE = 15 * 60  # seconds without a message or an event before the process is closed
EVERY = 60  # seconds between idle checks
HEARD = 60  # seconds a window's last report counts: a window not heard from is not focused
ALLOW = {"behavior": "allow"}
# (chat, kind), title, body, click -> sent? Rate limit and Settings toggle live behind it.
Popup = Callable[[tuple[str, str], str, str, Click], bool]


class Full(Exception):
    """A 4th live chat process, or a change while Claude answers: the page shows why (409)."""


@dataclass
class Chat:
    id: str
    project: str | None
    model: str
    effort: str
    cwd: Path
    # Told with `--append-system-prompt` on every open, so a resumed chat knows it too.
    context: Context | None = None
    sprint: int | None = None  # with a project: what `context` was built from
    step: str | None = None
    title: str = ""  # empty until the first send names it
    created: datetime = field(default_factory=datetime.now)
    stamp: datetime = field(default_factory=datetime.now)  # last message sent, as the vault has it
    saved: bool = False  # in the vault: set by the first send
    open: bool = True  # in the sidebar
    # Loaded from the vault at hubd start: its turns and context are rebuilt when it is first used.
    restored: bool = False
    hidden: bool = False  # the session file gave no turns: the page says "earlier turns not shown"
    used: float = field(default_factory=time.monotonic)  # last message or event
    # One turn = the message sent and the events it got (as `chat` events, text deltas joined).
    # `done`: it ended.
    turns: list[dict[str, Any]] = field(default_factory=list)
    allowed: set[str] = field(default_factory=set)  # tools Anis allowed for this chat
    # Cards waiting for Anis: request id -> (answer, can "Allow for this chat" cover it).
    asking: dict[str, tuple[asyncio.Future[str], bool]] = field(default_factory=dict)

    @property
    def system(self) -> str | None:
        return self.context.text if self.context else None

    @property
    def kind(self) -> str:
        return (
            "step"
            if self.step
            else "sprint"
            if self.sprint
            else "project"
            if self.project
            else "none"
        )

    @property
    def scratch(self) -> bool:
        return self.project is None

    @property
    def busy(self) -> bool:
        return any(not t["done"] for t in self.turns)


class Chats:
    def __init__(
        self,
        runner: Callable[[ChatEvent], ChatRunner],
        emit: Callable[[dict], None],
        vault: Path,
        context: Callable[[str, int | None, str | None], Awaitable[Context]],
        transcript: Transcript = no_transcript,
        popup: Popup = lambda *_: False,
        workspace: Callable[[str], int | None] = lambda _: None,
        account: Callable[[str], str] = lambda _: "claude",
        graph: Callable[[str], Path | None] = lambda _: None,
    ):
        self.runner = runner(self.on_event)
        self.runner.ask = self.ask
        self.emit = emit
        self.vault = vault
        self.build = context  # what a project chat is told, built again when it resumes
        self.transcript = transcript
        self.chats: dict[str, Chat] = {}
        self.ask_wait = permits.ASK_WAIT
        self.popup = popup
        self.workspace = workspace  # a project's Hyprland workspace, read at each open
        self.account = account  # and its Claude login
        self.graph = graph  # its graph.json when `graph: on`: graphify reads of it need no card
        self.clock = time.monotonic  # tests move it
        # Each page window's last report: window id -> (focused, chat it shows, when).
        self.windows: dict[str, tuple[bool, str | None, float]] = {}
        self.last: str | None = None  # the window that had focus last: a click goes to it

    def present(self, window: str, focused: bool, chat: str | None) -> None:
        """A page says whether its window has focus and which chat it shows."""
        now = self.clock()
        kept = {w: r for w, r in self.windows.items() if now - r[2] < HEARD}
        self.windows = {**kept, window: (focused, chat, now)}
        if focused:
            self.last = window

    def watched(self, chat_id: str) -> bool:
        """Does a focused window, heard from lately, show this chat?"""
        now = self.clock()
        return any(f and c == chat_id and now - t < HEARD for f, c, t in self.windows.values())

    def _tell(self, chat: Chat, kind: str, title: str, body: str) -> None:
        """A desktop popup for `chat`: Claude waits and Anis is not looking at it."""
        if self.watched(chat.id):
            return
        loop = asyncio.get_running_loop()  # a click comes from the notify-send thread
        self.popup((chat.id, kind), title, body, lambda: self._clicked(chat.id, loop))

    def _clicked(self, chat_id: str, loop: asyncio.AbstractEventLoop) -> None:
        focus.open_chat(chat_id)  # opens or focuses a window, which keeps the screen it shows
        with suppress(RuntimeError):  # hubd shut down while the popup was open
            loop.call_soon_threadsafe(self._goto, chat_id)

    def _goto(self, chat_id: str) -> None:
        """Tell the window Anis used last to show the chat."""
        if self.last:
            self.emit({"type": "goto", "window": self.last, "hash": f"#/chat/{chat_id}"})

    def _label(self, chat: Chat) -> str:
        return chat.title or chat.project or "New chat"

    def get(self, chat_id: str) -> Chat:
        if chat_id not in self.chats:
            raise NotFound(f"no chat {chat_id}")
        return self.chats[chat_id]

    def restore(self, repos: Mapping[str, Path | None]) -> None:
        """Read the saved chats of the vault: `repos` is each project's repo. No process starts."""
        scratch = self.vault / "chats" / "scratch"
        for project, cwd in [(None, scratch), *repos.items()]:
            if cwd is None:  # without its repo a project chat cannot resume
                continue
            for e in chatlog.load(chatlog.path_of(self.vault, project)):
                self.chats[e.id] = Chat(
                    e.id, project, e.model, e.effort, cwd, None, e.sprint, e.step, e.title,
                    e.created, e.used, True, e.open, True,
                )  # fmt: skip

    async def load(self, chat_id: str) -> Chat:
        """The chat, with the turns and context of a restored one read first (once)."""
        chat = self.get(chat_id)
        if chat.restored:
            chat.restored = False
            turns = await asyncio.to_thread(self.transcript, chat.id)
            chat.hidden = turns is None
            chat.turns = turns or []
            if chat.project:  # an earlier open told Claude this; a resume needs it again
                with suppress(NotFound, OSError):
                    chat.context = await self.build(chat.project, chat.sprint, chat.step)
        return chat

    def live(self, chat_id: str) -> bool:
        return chat_id in self.runner.chats

    def _room(self, chat_id: str | None = None) -> None:
        live = list(self.runner.chats)
        if chat_id not in live and len(live) >= MAX_LIVE:
            names = ", ".join(live)
            raise Full(f"{MAX_LIVE} chats are open already ({names}): stop one first")

    async def open(
        self,
        project: str | None,
        cwd: Path,
        model: str,
        effort: str,
        context: Context | None,
        sprint: int | None = None,
        step: str | None = None,
    ) -> Chat:
        self._room()
        chat = Chat(str(uuid.uuid4()), project, model, effort, cwd, context, sprint, step)
        self.chats[chat.id] = chat
        await self._start(chat)
        return chat

    async def _start(self, chat: Chat) -> None:
        workspace = self.workspace(chat.project) if chat.project else None
        account = self.account(chat.project) if chat.project else "claude"
        await self.runner.open(
            chat.id,
            chat.cwd,
            chat.model,
            chat.effort,
            chat.system,
            chat.scratch,
            workspace,
            account,
        )

    async def send(self, chat_id: str, text: str) -> None:
        chat = await self.load(chat_id)
        chat.used = time.monotonic()
        if not self.live(chat_id):
            self._room(chat_id)
            await self._start(chat)
        chat.title = chat.title or chatlog.title_of(text)
        chat.open, chat.stamp = True, datetime.now()
        self._save(chat)
        chat.turns.append({"text": text, "events": [], "done": False})
        await self.runner.send(chat_id, text)

    def _save(self, chat: Chat) -> None:
        """The chat's line in the vault (written on the first send, then kept up to date)."""
        entry = chatlog.ChatEntry(
            chat.id, chat.title, chat.model, chat.effort, chat.kind, chat.created, chat.stamp,
            chat.sprint, chat.step, chat.open,
        )  # fmt: skip
        chatlog.save(chatlog.path_of(self.vault, chat.project), entry)
        chat.saved = True
        self.emit({"type": "chats"})

    def listing(self) -> list[dict]:
        """The saved chats, last used first: the sidebar's open ones and the Chats screen's."""
        saved = sorted((c for c in self.chats.values() if c.saved), key=lambda c: c.stamp)
        return [
            {
                "id": c.id,
                "project": c.project,
                "title": c.title,
                "model": c.model,
                "effort": c.effort,
                "used": int(c.stamp.timestamp() * 1000),
                "open": c.open,
            }
            for c in reversed(saved)
        ]

    async def update(self, chat_id: str, model: str | None, effort: str | None) -> Chat:
        """New model or effort: a live process is closed and resumed with the new flag."""
        chat = await self.load(chat_id)
        if chat.busy:  # closing now would cut the answer
            raise Full("Claude is answering: change model or effort when it is done")
        chat.model, chat.effort = model or chat.model, effort or chat.effort
        if chat.saved:
            self._save(chat)
        if self.live(chat_id):
            await self.runner.stop(chat_id)
            await self._start(chat)
        return chat

    async def edit(self, chat_id: str, title: str | None, open: bool | None) -> Chat:
        """Rename the chat (kept in the vault only), or close it: out of the sidebar, entry kept."""
        chat = await self.load(chat_id)
        if title is not None:
            chat.title = one_line(title)
        if open is False and self.live(chat_id):  # a closed chat holds no process
            await self.stop(chat_id)
        if open is not None:
            chat.open = open
        if chat.saved:
            self._save(chat)
        return chat

    async def stop(self, chat_id: str) -> None:
        """End the process, mid-turn or not. The next message resumes the chat."""
        chat = self.get(chat_id)
        for future, _ in chat.asking.values():  # Claude gets a deny before it goes
            if not future.done():
                future.set_result("stopped")
        await self.runner.stop(chat_id, now=True)
        if chat.busy:  # the turn got no `turn_end`
            await self.on_event(chat_id, {"type": "stopped"})

    async def ask(self, chat_id: str, tool: str, tool_input: dict[str, Any]) -> dict[str, str]:
        """Claude wants to run `tool`: a card in the chat, and Anis's answer for Claude."""
        if (chat := self.chats.get(chat_id)) is None:
            return {"behavior": "deny", "message": "This chat is closed."}
        card = {"tool": tool, **permits.card(tool, tool_input)}
        if why := permits.refuse(tool, tool_input, chat.cwd, chat.scratch):
            await self.on_event(chat_id, {"type": "permission_refused", **card, "message": why})
            return {"behavior": "deny", "message": why}
        if chat.project and permits.graph_read(tool, tool_input, self.graph(chat.project)):
            return ALLOW
        wide = permits.chat_wide(tool, tool_input, chat.cwd)
        if wide and tool in chat.allowed:
            return ALLOW
        request = uuid.uuid4().hex[:12]
        future = asyncio.get_running_loop().create_future()
        chat.asking[request] = (future, wide)
        await self.on_event(
            chat_id, {"type": "permission", "request": request, **card, "wide": wide}
        )
        self._tell(chat, "permission", "Claude needs permission", permits.short(tool, tool_input))
        minutes = round(self.ask_wait / 60)
        try:
            answer = await asyncio.wait_for(future, self.ask_wait)
        except TimeoutError:
            answer = "timeout"
            self._tell(chat, "timeout", f"Permission denied after {minutes} min", self._label(chat))
        finally:
            chat.asking.pop(request, None)
        if answer == "chat":
            chat.allowed.add(tool)
        message = {
            "deny": "Anis denied this call. Do not retry it; ask him or go on without it.",
            "timeout": f"No answer from Anis in {minutes} min, so it was denied. Do not retry it.",
            "stopped": "Anis stopped the chat.",
        }.get(answer)
        await self.on_event(
            chat_id, {"type": "permission_answer", "request": request, "answer": answer}
        )
        return {"behavior": "deny", "message": message} if message else ALLOW

    def answer(self, chat_id: str, request: str, answer: str) -> None:
        """Anis pressed Allow (`allow`), Deny (`deny`) or Allow for this chat (`chat`)."""
        future, wide = self.get(chat_id).asking.get(request, (None, False))
        if future is None or future.done():
            raise NotFound(f"no permission card {request} waits in chat {chat_id}")
        future.set_result("allow" if answer == "chat" and not wide else answer)

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
        if chat and kind == "turn_end":
            self._tell(chat, "turn", "Claude answered", self._label(chat))

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
            "context": chat.context.json() if chat.context else None,
            "title": chat.title,
            "open": chat.open,
            "live": self.live(chat.id),
            "busy": chat.busy,
            "earlier_hidden": chat.hidden,
            "turns": chat.turns,
        }
