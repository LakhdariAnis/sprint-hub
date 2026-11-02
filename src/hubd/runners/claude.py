"""Run a real Claude Code session in a new terminal. Documented CLI flags only (ROADMAP rule 4)."""

import asyncio
import os
import shutil
import subprocess
from pathlib import Path

from hubd import install
from hubd.model import Step
from hubd.states import InvalidTransition

# Every flag below is in https://code.claude.com/docs/en/cli-reference (checked 2026-10-16).
# `claude "query"` starts an interactive session with that first prompt (same page, "CLI commands").
MODEL = "--model"  # model alias or full name
SESSION_ID = "--session-id"  # must be a valid UUID
RESUME = "--resume"  # session ID or name
GRACE = 0.3  # seconds a terminal gets to fail on bad arguments, before the start counts as launched


class ClaudeCodeRunner:
    def __init__(self, terminal: list[str], hub_url: str, settings: Path = install.SETTINGS):
        self.terminal = terminal
        self.hub_url = hub_url
        self.settings = settings  # Claude's settings.json, where the hook must be

    def refusal(self, step_id: str, cwd: Path, fresh: bool) -> str | None:
        # A resumed chat gets the review comment as its prompt, not the command.
        command = cwd / ".claude" / "commands" / f"sprint-{step_id}.md"
        if fresh and not command.is_file():
            return f"no {command}: without it, /sprint-{step_id} is not a command"
        if shutil.which("claude") is None:
            return "claude not on PATH of hubd: install it, then restart hubd"
        return install.hook_problem(self.settings)

    def command(self, cwd: Path, claude_args: list[str]) -> list[str]:
        """The terminal argv with `{cwd}` filled in, then `claude` and its args."""
        return [arg.replace("{cwd}", str(cwd)) for arg in self.terminal] + ["claude", *claude_args]

    def env(self, step: Step) -> dict[str, str]:
        return {**os.environ, "HUB_RUN": step.step, "HUB_URL": self.hub_url}

    async def start(self, step: Step, session_id: str, model: str, cwd: Path, prompt: str) -> None:
        args = [MODEL, model, SESSION_ID, session_id, prompt]
        await self._spawn(self.command(cwd, args), cwd, self.env(step))

    async def resume(self, step: Step, session_id: str, cwd: Path, prompt: str) -> None:
        await self._spawn(self.command(cwd, [RESUME, session_id, prompt]), cwd, self.env(step))

    async def _spawn(self, argv: list[str], cwd: Path, env: dict[str, str]) -> None:
        # Own session: the terminal outlives hubd; the run's end comes back through the hook.
        try:
            process = subprocess.Popen(
                argv,
                cwd=cwd,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as exc:
            raise InvalidTransition(f"terminal did not launch: {exc}; see hub.toml") from exc
        await asyncio.sleep(GRACE)
        # Exit 0 is fine: a terminal may hand the window to an instance already running.
        if code := process.poll():
            raise InvalidTransition(f"terminal {argv[0]} exited with code {code}; see hub.toml")
