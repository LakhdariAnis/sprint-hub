"""The one interface hubd uses to run an agent (docs/ROADMAP.md rule 4)."""

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Protocol

from hubd.model import Step

# Called once when a run ends: (session_id, step id).
RunEnded = Callable[[str, str], Awaitable[None]]


class AgentRunner(Protocol):
    """Both methods return once the run is launched. The end comes later, through `RunEnded`."""

    async def start(
        self, step: Step, session_id: str, model: str, cwd: Path, prompt: str
    ) -> None: ...

    async def resume(self, session_id: str, cwd: Path, prompt: str) -> None: ...
