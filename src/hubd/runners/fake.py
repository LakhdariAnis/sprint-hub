"""A runner that behaves like Claude without Claude: ticks the checklist, then reports the end."""

import asyncio
from asyncio import sleep
from pathlib import Path

from hubd.model import Step
from hubd.runners.base import RunEnded
from hubd.runners.chat import ChatEvent, no_one
from hubd.vault import split_sections


class FakeRunner:
    def __init__(self, run_ended: RunEnded, delay: float = 0.5):
        self.run_ended = run_ended
        self.delay = delay
        self.tasks: dict[str, asyncio.Task[None]] = {}  # keeps runs alive; tests await them
        self.resumed: list[tuple[str, str]] = []  # (session_id, prompt) of each resume
        self.started: list[tuple[str, str]] = []  # (session_id, prompt) of each new chat
        self.focused: list[int] = []  # workspaces asked for; the fake never calls `hyprctl`
        self.ended: set[str] = set()  # sessions whose fake run ended: their chat can reopen

    def refusal(
        self, step_id: str, cwd: Path, fresh: bool, running: str | None, account: str = "claude"
    ) -> None:
        return None  # it only writes a progress file, so the demo can run steps side by side

    def running(self, session_id: str) -> bool:
        # The demo's `doing` steps show a run in progress; a fake run that ended is gone.
        return session_id not in self.ended

    async def focus(self, workspace: int) -> None:
        self.focused.append(workspace)

    async def start(
        self,
        step: Step,
        session_id: str,
        model: str,
        cwd: Path,
        prompt: str,
        workspace: int | None = None,
        account: str = "claude",
    ) -> None:
        self.started.append((session_id, prompt))
        self.ended.discard(session_id)
        self.tasks[session_id] = asyncio.create_task(self._run(session_id, step.step, cwd))

    async def resume(
        self,
        step: Step,
        session_id: str,
        cwd: Path,
        prompt: str,
        workspace: int | None = None,
        account: str = "claude",
    ) -> None:
        self.resumed.append((session_id, prompt))
        self.ended.discard(session_id)
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
        self.ended.add(session_id)
        await self.run_ended(session_id, step_id)


REPLY = ["This is ", "a fake ", "answer. ", "The folder ", "has one file."]
# `md …` gets this: each markdown construct, the fence split like a stream, markup left as text.
MARKDOWN = [
    "## Hello\n\nSome **bold**, `code` and [a link](https://example.org/x).\n\n",
    "- one\n  - nested\n- two\n\n",
    "```python\nprint(",
    "'hi')\n```\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n",
    "<b>hi</b><script>window.__xss = 1</script>",
]
TOOL = {
    "type": "tool",
    "id": "fake_tool",
    "name": "Bash",
    "line": "Bash ls",
    "input": "command: ls",
}
TOOL_RESULT = {"type": "tool_result", "id": "fake_tool", "error": False, "text": "README.md"}
# A message that starts with "graph" asks the demo project's graph instead (657).
GRAPH_COMMAND = (
    'graphify affected "list_items()" --relation calls --relation imports_from --depth 3 '
    "--graph graph.json"
)
GRAPH_TOOL = TOOL | {
    "line": "Asked the graph: affected list_items() --relation calls --relation imports_from"
    " --depth 3",
    "input": f"command: {GRAPH_COMMAND}",
}
GRAPH_RESULT = TOOL_RESULT | {
    "text": "- serve() [calls] src/api.py:L9\n- draw_list() [calls] src/ui.py:L6"
}


class FakeChat:
    """ChatRunner without Claude: each message gets REPLY in deltas, one tool call, `turn_end`.

    A message "run <command>" asks permission for Bash first, as Claude would. A message that
    starts with "stall" takes 40 times longer, one that starts with "graph" asks the graph.
    """

    def __init__(self, on_event: ChatEvent, delay: float = 0.05):
        self.on_event = on_event
        self.delay = delay
        self.turns: dict[str, asyncio.Task[None]] = {}  # the turn under way, per open chat
        self.chats: set[str] = set()
        self.models: dict[str, str] = {}
        self.ask = no_one
        self.opened: list[tuple[str, str, str | None]] = []  # (chat id, model, effort) per open
        self.systems: list[str | None] = []  # `system` per open
        self.workspaces: list[int | None] = []  # `workspace` per open

    async def open(
        self,
        chat_id: str,
        cwd: Path,
        model: str,
        effort: str | None,
        system: str | None = None,
        scratch: bool = False,
        workspace: int | None = None,
        account: str = "claude",
    ) -> None:
        self.opened.append((chat_id, model, effort))
        self.models[chat_id] = model
        self.systems.append(system)
        self.workspaces.append(workspace)
        self.chats.add(chat_id)

    async def send(self, chat_id: str, text: str) -> None:
        if chat_id not in self.chats:
            await self.on_event(chat_id, {"type": "error", "message": "chat is not open"})
            return
        # Like claude, a message sent mid-turn waits for the turn before it.
        previous = self.turns.get(chat_id)
        self.turns[chat_id] = asyncio.create_task(self._turn(chat_id, text, previous))

    async def stop(self, chat_id: str, now: bool = False) -> None:
        self.chats.discard(chat_id)
        if task := self.turns.pop(chat_id, None):
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def close(self, chat_id: str) -> None:
        await self.stop(chat_id)

    async def _turn(self, chat_id: str, text: str, previous: asyncio.Task[None] | None) -> None:
        if previous:
            await asyncio.gather(previous, return_exceptions=True)
        reply = REPLY
        delay = self.delay * 40 if text.startswith("stall") else self.delay  # time to press Stop
        if text.startswith("md "):
            reply = MARKDOWN
        if text.startswith("run "):
            answer = await self.ask(chat_id, "Bash", {"command": text.removeprefix("run ")})
            if answer["behavior"] != "allow":
                reply = [f"Not run: {answer['message']}"]
        for piece in reply[:3]:
            await self.on_event(chat_id, {"type": "text", "text": piece})
            await sleep(delay)
        if reply is REPLY:
            graph = text.startswith("graph")
            await self.on_event(chat_id, GRAPH_TOOL if graph else TOOL)
            await sleep(delay)
            await self.on_event(chat_id, GRAPH_RESULT if graph else TOOL_RESULT)
        for piece in reply[3:]:
            await self.on_event(chat_id, {"type": "text", "text": piece})
            await sleep(delay)
        end = {
            "type": "turn_end",
            "model": self.models.get(chat_id),
            "cost_usd": 0.02,
            "input_tokens": 4100,
            "output_tokens": 380,
        }
        await self.on_event(chat_id, end | {"duration_ms": int(delay * 1000 * len(reply))})


def _spec_tasks(cwd: Path, step_id: str) -> list[str]:
    """`- ` lines under `## Tasks` in `sprint/<id>-*.md`."""
    spec = next(iter(sorted(cwd.glob(f"sprint/{step_id}-*.md"))), None)
    if spec is None:
        raise FileNotFoundError(f"no spec sprint/{step_id}-*.md in {cwd}")
    lines = split_sections(spec.read_text()).get("Tasks", [])
    return [line.removeprefix("- ") for line in lines if line.startswith("- ")]
