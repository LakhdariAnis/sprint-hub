"""The one interface hubd uses to run an agent (docs/ROADMAP.md rule 4)."""

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Protocol

from hubd.model import Step

# Called once when a run ends: (session_id, step id).
RunEnded = Callable[[str, str], Awaitable[None]]


class AgentRunner(Protocol):
    """`start` and `resume` return once the run is launched. The end comes later: `RunEnded`."""

    def refusal(self, step_id: str, cwd: Path, fresh: bool, running: str | None) -> str | None:
        """Why this run must not start, checked before any file changes; None = go.

        `fresh`: a new chat with the step's command, not a resumed one.
        `running`: the step with a run in `cwd` right now, if any.
        """
        ...

    def running(self, session_id: str) -> bool:
        """Is this session alive right now? Asked when hubd starts."""
        ...

    async def start(
        self, step: Step, session_id: str, model: str, cwd: Path, prompt: str
    ) -> None: ...

    async def resume(self, step: Step, session_id: str, cwd: Path, prompt: str) -> None: ...
