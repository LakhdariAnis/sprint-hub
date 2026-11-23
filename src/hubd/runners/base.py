"""The one interface hubd uses to run an agent (docs/ROADMAP.md rule 4)."""

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Protocol

from hubd.model import Step

# Called once when a run ends: (session_id, step id).
RunEnded = Callable[[str, str], Awaitable[None]]


class Unavailable(Exception):
    """The desktop cannot do it right now (no `hyprctl`, or it refused): the API says 503."""


class AgentRunner(Protocol):
    """`start` and `resume` return once the run is launched. The end comes later: `RunEnded`."""

    def refusal(
        self, step_id: str, cwd: Path, fresh: bool, running: str | None, account: str = "claude"
    ) -> str | None:
        """Why this run must not start, checked before any file changes; None = go.

        `fresh`: a new chat with the step's command, not a resumed one.
        `running`: the step with a run in `cwd` right now, if any.
        """
        ...

    def running(self, session_id: str) -> bool:
        """Is this session alive right now? Asked when hubd starts."""
        ...

    async def focus(self, workspace: int) -> None:
        """Switch the desktop to this Hyprland workspace; raises `Unavailable` with the reason."""
        ...

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
        """`workspace`: the project's Hyprland workspace for the run's terminal; None = anywhere.

        `account`: which Claude login the run uses (`Project.account`).
        """
        ...

    async def resume(
        self,
        step: Step,
        session_id: str,
        cwd: Path,
        prompt: str,
        workspace: int | None = None,
        account: str = "claude",
    ) -> None: ...
