"""Run a real Claude Code session in a new terminal. Documented CLI flags only (ROADMAP rule 4)."""

import asyncio
import shlex
import shutil
import subprocess
from pathlib import Path

from hubd import install, session
from hubd.model import Step
from hubd.runners.base import Unavailable
from hubd.states import InvalidTransition

# Every flag below is in https://code.claude.com/docs/en/cli-reference (checked 2026-10-16).
# `claude "query"` starts an interactive session with that first prompt (same page, "CLI commands").
MODEL = "--model"  # model alias or full name
SESSION_ID = "--session-id"  # must be a valid UUID
RESUME = "--resume"  # session ID or name
HYPRCTL_WAIT = 5  # seconds hyprctl gets to answer
GRACE = 0.3  # seconds a terminal gets to fail on bad arguments, before the start counts as launched


class ClaudeCodeRunner:
    def __init__(self, terminal: list[str], hub_url: str, settings: Path = install.SETTINGS):
        self.terminal = terminal
        self.hub_url = hub_url
        self.settings = settings  # Claude's settings.json, where the hook must be

    def refusal(self, step_id: str, cwd: Path, fresh: bool, running: str | None) -> str | None:
        # Two sessions in one work tree would switch branches under each other.
        if running:
            return f"step {running} is running in this repo, wait for it to end"
        # A resumed chat gets the review comment as its prompt, not the command.
        command = cwd / ".claude" / "commands" / f"sprint-{step_id}.md"
        if fresh and not command.is_file():
            return f"no {command}: without it, /sprint-{step_id} is not a command"
        if shutil.which("claude") is None:
            return "claude not on PATH of hubd: install it, then restart hubd"
        return install.hook_problem(self.settings)

    def running(self, session_id: str) -> bool:
        # `--session-id` or `--resume` holds it: on the argv of `claude` and of its terminal.
        for cmdline in Path("/proc").glob("[0-9]*/cmdline"):
            try:
                if session_id.encode() in cmdline.read_bytes():
                    return True
            except OSError:
                continue  # that process just ended
        return False

    def command(
        self, step: Step, cwd: Path, claude_args: list[str], workspace: int | None = None
    ) -> list[str]:
        """The terminal argv with `{cwd}` filled in, then `claude` and its args.

        With a workspace and `hyprctl` on PATH: `hyprctl dispatch exec` opens it there, without
        switching to it. Hyprland starts that process, not hubd, so the hook's env goes on it.
        """
        argv = [arg.replace("{cwd}", str(cwd)) for arg in self.terminal] + ["claude", *claude_args]
        if workspace is None or shutil.which("hyprctl") is None:
            return argv
        env = [f"HUB_RUN={step.step}", f"HUB_URL={self.hub_url}"]
        line = shlex.join(["env", *env, *argv])  # run by `sh -c`: a path with spaces needs quotes
        return ["hyprctl", "dispatch", "exec", f"[workspace {workspace} silent] {line}"]

    def env(self, step: Step) -> dict[str, str]:
        return {**session.env(), "HUB_RUN": step.step, "HUB_URL": self.hub_url}

    async def start(
        self,
        step: Step,
        session_id: str,
        model: str,
        cwd: Path,
        prompt: str,
        workspace: int | None = None,
    ) -> None:
        args = [MODEL, model, SESSION_ID, session_id, prompt]
        await self._launch(step, cwd, args, workspace)

    async def resume(
        self, step: Step, session_id: str, cwd: Path, prompt: str, workspace: int | None = None
    ) -> None:
        await self._launch(step, cwd, [RESUME, session_id, prompt], workspace)

    async def _launch(
        self, step: Step, cwd: Path, claude_args: list[str], workspace: int | None
    ) -> None:
        argv = self.command(step, cwd, claude_args, workspace)
        if argv[0] == "hyprctl":
            await self._hypr(argv, self.env(step))
        else:
            await self._spawn(argv, cwd, self.env(step))

    async def focus(self, workspace: int) -> None:
        if shutil.which("hyprctl") is None:
            raise Unavailable("hyprctl not on PATH of hubd: workspaces need Hyprland")
        argv = ["hyprctl", "dispatch", "workspace", str(workspace)]
        try:
            done = await asyncio.to_thread(
                subprocess.run,
                argv,
                env=session.env(),
                capture_output=True,
                text=True,
                timeout=HYPRCTL_WAIT,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise Unavailable(f"hyprctl failed: {exc}") from exc
        if (out := done.stdout.strip()) != "ok":
            raise Unavailable(f"hyprctl said {out or done.stderr.strip() or 'nothing'}")

    async def _hypr(self, argv: list[str], env: dict[str, str]) -> None:
        # hyprctl prints `ok` and exits 0 even when the terminal never starts, so only a missing
        # terminal and a refused dispatch are caught here; a terminal that exits at once is not.
        if shutil.which(self.terminal[0]) is None:
            raise InvalidTransition(
                f"terminal did not launch: {self.terminal[0]} not on PATH; see hub.toml"
            )
        try:
            done = await asyncio.to_thread(
                subprocess.run, argv, env=env, capture_output=True, text=True, timeout=HYPRCTL_WAIT
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise InvalidTransition(f"terminal did not launch: {exc}; see hub.toml") from exc
        if (out := done.stdout.strip()) != "ok":
            raise InvalidTransition(
                f"terminal did not launch: hyprctl said {out or done.stderr.strip() or 'nothing'}"
            )

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
