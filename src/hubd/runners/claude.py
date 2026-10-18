"""Run a real Claude Code session in a new terminal. Documented CLI flags only (ROADMAP rule 4)."""

import os
import subprocess
from pathlib import Path

from hubd.model import Step

# Every flag below is in https://code.claude.com/docs/en/cli-reference (checked 2026-10-16).
# `claude "query"` starts an interactive session with that first prompt (same page, "CLI commands").
MODEL = "--model"  # model alias or full name
SESSION_ID = "--session-id"  # must be a valid UUID
RESUME = "--resume"  # session ID or name


class ClaudeCodeRunner:
    def __init__(self, terminal: list[str], hub_url: str):
        self.terminal = terminal
        self.hub_url = hub_url

    def command(self, cwd: Path, claude_args: list[str]) -> list[str]:
        """The terminal argv with `{cwd}` filled in, then `claude` and its args."""
        return [arg.replace("{cwd}", str(cwd)) for arg in self.terminal] + ["claude", *claude_args]

    def env(self, step: Step) -> dict[str, str]:
        return {**os.environ, "HUB_RUN": step.step, "HUB_URL": self.hub_url}

    async def start(self, step: Step, session_id: str, model: str, cwd: Path, prompt: str) -> None:
        args = [MODEL, model, SESSION_ID, session_id, prompt]
        self._spawn(self.command(cwd, args), cwd, self.env(step))

    async def resume(self, step: Step, session_id: str, cwd: Path, prompt: str) -> None:
        self._spawn(self.command(cwd, [RESUME, session_id, prompt]), cwd, self.env(step))

    def _spawn(self, argv: list[str], cwd: Path, env: dict[str, str]) -> None:
        # Own session: the terminal outlives hubd; the run's end comes back through the hook.
        subprocess.Popen(
            argv,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
