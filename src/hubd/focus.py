"""A click on a "waits for you" popup: focus the run's terminal, else open the app at the step.

A chat popup opens the app at the chat.
"""

import json
import subprocess
from pathlib import Path

from hubd import session

APP = Path(__file__).resolve().parents[2] / "bin" / "sprint-hub-app"


def _parent(proc: Path, pid: int) -> int | None:
    try:
        stat = (proc / str(pid) / "stat").read_text()
    except OSError:
        return None
    return int(stat.rpartition(")")[2].split()[1])  # after `(comm)`, which may hold spaces


def window_pid(session_id: str, windows: set[int], proc: Path = Path("/proc")) -> int | None:
    """The pid of the window that holds the process with `session_id` on its argv, if any."""
    for cmdline in proc.glob("[0-9]*/cmdline"):
        try:
            if session_id.encode() not in cmdline.read_bytes():
                continue
        except OSError:
            continue  # that process just ended
        pid: int | None = int(cmdline.parent.name)
        while pid and pid not in windows:  # claude runs inside the terminal's window
            pid = _parent(proc, pid)
        if pid:
            return pid
    return None


def _windows(env: dict[str, str]) -> set[int]:
    try:
        out = subprocess.run(
            ["hyprctl", "clients", "-j"], capture_output=True, text=True, timeout=5, env=env
        ).stdout
        return {c["pid"] for c in json.loads(out)}
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
        return set()  # no Hyprland: fall back to the app


def open_run(session_id: str, project: str, step: str, workspace: int | None = None) -> None:
    env = session.env()
    try:
        windows = _windows(env)
        if pid := window_pid(session_id, windows):
            subprocess.run(
                ["hyprctl", "dispatch", f'hl.dsp.focus({{ window = "pid:{pid}" }})'],
                env=env,
                timeout=5,
            )
        elif (
            workspace and windows
        ):  # terminal not found (a server terminal?): at least its workspace
            subprocess.run(
                ["hyprctl", "dispatch", f'hl.dsp.focus({{ workspace = "{workspace}" }})'],
                env=env,
                timeout=5,
            )
        else:
            subprocess.Popen([str(APP), f"#/step/{project}/{step}"], env=env)
    except (OSError, subprocess.SubprocessError):
        pass  # a click that does nothing must never stop the hub


def open_chat(chat_id: str) -> None:
    try:
        subprocess.run([str(APP), f"#/chat/{chat_id}"], env=session.env(), timeout=10)
    except (OSError, subprocess.SubprocessError):
        pass  # a click that does nothing must never stop the hub
