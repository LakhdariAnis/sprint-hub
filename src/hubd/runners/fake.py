"""A runner that behaves like Claude without Claude: ticks the checklist, then reports the end."""

import asyncio
from asyncio import sleep
from pathlib import Path

from hubd.model import Step
from hubd.runners.base import RunEnded
from hubd.runners.chat import ChatEvent
from hubd.vault import split_sections


class FakeRunner:
    def __init__(self, run_ended: RunEnded, delay: float = 0.5):
        self.run_ended = run_ended
        self.delay = delay
        self.tasks: dict[str, asyncio.Task[None]] = {}  # keeps runs alive; tests await them
        self.resumed: list[tuple[str, str]] = []  # (session_id, prompt) of each resume
        self.started: list[tuple[str, str]] = []  # (session_id, prompt) of each new chat

    def refusal(self, step_id: str, cwd: Path, fresh: bool, running: str | None) -> None:
        return None  # it only writes a progress file, so the demo can run steps side by side

    def running(self, session_id: str) -> bool:
        return True  # the demo's `doing` steps show a run in progress

    async def start(self, step: Step, session_id: str, model: str, cwd: Path, prompt: str) -> None:
        self.started.append((session_id, prompt))
        self.tasks[session_id] = asyncio.create_task(self._run(session_id, step.step, cwd))

    async def resume(self, step: Step, session_id: str, cwd: Path, prompt: str) -> None:
        self.resumed.append((session_id, prompt))
        self.tasks[session_id] = asyncio.create_task(self._run(session_id, step.step, cwd))

    async def _run(self, session_id: str, step_id: str, cwd: Path) -> None:
        tasks = _spec_tasks(cwd, step_id)
        marks = [" "] * len(tasks)
        progress = cwd / "sprint" / "progress" / f"{step_id}.md"
        progress.parent.mkdir(parents=True, exist_ok=True)

        async def write() -> None:
            lines = [f"# Step {step_id}"] + [
                f"- [{m}] {t}" for m, t in zip(marks, tasks, strict=True)
            ]
            progress.write_text("\n".join(lines) + "\n")
            await sleep(self.delay)

        await write()
        for i in range(len(tasks)):
            marks[i] = "~"
            await write()
            marks[i] = "x"
            await write()
        await self.run_ended(session_id, step_id)


REPLY = ["This is ", "a fake ", "answer. ", "The folder ", "has one file."]
TOOL = {"type": "tool", "id": "fake_tool", "name": "Bash", "input": "ls"}
TOOL_RESULT = {"type": "tool_result", "id": "fake_tool", "error": False, "text": "README.md"}


class FakeChat:
    """ChatRunner without Claude: each message gets REPLY in deltas, one tool call, `turn_end`."""

    def __init__(self, on_event: ChatEvent, delay: float = 0.05):
        self.on_event = on_event
        self.delay = delay
        self.turns: dict[str, asyncio.Task[None]] = {}  # the turn under way, per open chat
        self.chats: set[str] = set()
        self.opened: list[tuple[str, str, str | None]] = []  # (chat id, model, effort) per open
        self.systems: list[str | None] = []  # `system` per open

    async def open(
        self, chat_id: str, cwd: Path, model: str, effort: str | None, system: str | None = None
    ) -> None:
        self.opened.append((chat_id, model, effort))
        self.systems.append(system)
        self.chats.add(chat_id)

    async def send(self, chat_id: str, text: str) -> None:
        if chat_id not in self.chats:
            await self.on_event(chat_id, {"type": "error", "message": "chat is not open"})
            return
        # Like claude, a message sent mid-turn waits for the turn before it.
        previous = self.turns.get(chat_id)
        self.turns[chat_id] = asyncio.create_task(self._turn(chat_id, previous))

    async def stop(self, chat_id: str) -> None:
        self.chats.discard(chat_id)
        if task := self.turns.pop(chat_id, None):
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def close(self, chat_id: str) -> None:
        await self.stop(chat_id)

    async def _turn(self, chat_id: str, previous: asyncio.Task[None] | None) -> None:
        if previous:
            await asyncio.gather(previous, return_exceptions=True)
        for piece in REPLY[:3]:
            await self.on_event(chat_id, {"type": "text", "text": piece})
            await sleep(self.delay)
        await self.on_event(chat_id, TOOL)
        await sleep(self.delay)
        await self.on_event(chat_id, TOOL_RESULT)
        for piece in REPLY[3:]:
            await self.on_event(chat_id, {"type": "text", "text": piece})
            await sleep(self.delay)
        end = {"type": "turn_end", "cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0}
        await self.on_event(chat_id, end | {"duration_ms": int(self.delay * 1000 * len(REPLY))})


def _spec_tasks(cwd: Path, step_id: str) -> list[str]:
    """`- ` lines under `## Tasks` in `sprint/<id>-*.md`."""
    spec = next(iter(sorted(cwd.glob(f"sprint/{step_id}-*.md"))), None)
    if spec is None:
        raise FileNotFoundError(f"no spec sprint/{step_id}-*.md in {cwd}")
    lines = split_sections(spec.read_text()).get("Tasks", [])
    return [line.removeprefix("- ") for line in lines if line.startswith("- ")]
