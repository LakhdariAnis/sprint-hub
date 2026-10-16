"""A runner that behaves like Claude without Claude: ticks the checklist, then reports the end."""

import asyncio
from asyncio import sleep
from pathlib import Path

from hubd.model import Step
from hubd.runners.base import RunEnded
from hubd.vault import split_sections


class FakeRunner:
    def __init__(self, run_ended: RunEnded, delay: float = 0.5):
        self.run_ended = run_ended
        self.delay = delay
        self.steps: dict[str, str] = {}  # session_id -> step id, for resume
        self.tasks: dict[str, asyncio.Task[None]] = {}  # keeps runs alive; tests await them

    async def start(self, step: Step, session_id: str, model: str, cwd: Path, prompt: str) -> None:
        self.steps[session_id] = step.step
        self.tasks[session_id] = asyncio.create_task(self._run(session_id, step.step, cwd))

    async def resume(self, session_id: str, cwd: Path, prompt: str) -> None:
        step_id = self.steps[session_id]
        self.tasks[session_id] = asyncio.create_task(self._run(session_id, step_id, cwd))

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


def _spec_tasks(cwd: Path, step_id: str) -> list[str]:
    """`- ` lines under `## Tasks` in `sprint/<id>-*.md`."""
    spec = next(iter(sorted(cwd.glob(f"sprint/{step_id}-*.md"))), None)
    if spec is None:
        raise FileNotFoundError(f"no spec sprint/{step_id}-*.md in {cwd}")
    lines = split_sections(spec.read_text()).get("Tasks", [])
    return [line.removeprefix("- ") for line in lines if line.startswith("- ")]
