"""A window a run or a chat opens goes to its project's workspace, not the one Anis looks at.

hubd puts `HUB_WORKSPACE` on the processes it starts and every child inherits it, so the app
of a `flutter run` carries it too. A window handed to an instance already running (a link to
an open browser) belongs to that older process and stays where Hyprland put it.
"""

import asyncio
import json
import subprocess
from contextlib import suppress
from pathlib import Path

from hubd import session

VAR = "HUB_WORKSPACE"
RETRY = 5  # seconds between tries to reach Hyprland (hubd may start before it, or outlive it)


def opened(line: str) -> tuple[str, str] | None:
    """`openwindow>>ADDRESS,WORKSPACE,CLASS,TITLE` -> (`0xADDRESS`, workspace); else None."""
    kind, _, data = line.partition(">>")
    parts = data.split(",", 2)
    if kind != "openwindow" or len(parts) < 2:
        return None
    return f"0x{parts[0]}", parts[1]


def workspace_of(pid: int, proc: Path = Path("/proc")) -> str | None:
    """The `HUB_WORKSPACE` in the environment of `pid`, if it has one."""
    try:
        environ = (proc / str(pid) / "environ").read_bytes()
    except OSError:
        return None  # gone already, or not ours to read
    for item in environ.split(b"\0"):
        key, _, value = item.partition(b"=")
        if key == VAR.encode() and value.isdigit():  # it goes into a Lua string: digits only
            return value.decode()
    return None


def _pid(address: str, env: dict[str, str]) -> int | None:
    try:
        out = subprocess.run(
            ["hyprctl", "clients", "-j"], capture_output=True, text=True, timeout=5, env=env
        ).stdout
        return next((c["pid"] for c in json.loads(out) if c["address"] == address), None)
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
        return None


def place(line: str, env: dict[str, str], proc: Path = Path("/proc")) -> list[str] | None:
    """The `hyprctl` argv that moves the window `line` opened, or None when it stays."""
    if (event := opened(line)) is None:
        return None
    address, now = event
    if (pid := _pid(address, env)) is None or (target := workspace_of(pid, proc)) in (None, now):
        return None
    rules = f'workspace = "{target}", follow = false, window = "address:{address}"'
    return ["hyprctl", "dispatch", f"hl.dsp.window.move({{ {rules} }})"]


def _move(line: str, env: dict[str, str]) -> None:
    if argv := place(line, env):
        with suppress(OSError, subprocess.SubprocessError):
            subprocess.run(argv, env=env, capture_output=True, timeout=5)


async def loop(stop: asyncio.Event) -> None:
    """Follow Hyprland's events until `stop`; without Hyprland, try again every `RETRY` s."""
    while not stop.is_set():
        env = session.env()
        sig, runtime = env.get("HYPRLAND_INSTANCE_SIGNATURE"), env.get("XDG_RUNTIME_DIR")
        if sig and runtime:
            with suppress(OSError):
                path = Path(runtime) / "hypr" / sig / ".socket2.sock"
                reader, writer = await asyncio.open_unix_connection(path)
                try:
                    await _follow(reader, env, stop)
                finally:
                    writer.close()
        with suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), RETRY)


async def _follow(reader: asyncio.StreamReader, env: dict[str, str], stop: asyncio.Event) -> None:
    stopped = asyncio.create_task(stop.wait())
    try:
        while True:
            line = asyncio.create_task(reader.readline())
            await asyncio.wait({line, stopped}, return_when=asyncio.FIRST_COMPLETED)
            if not line.done():
                line.cancel()
                return
            if not (raw := line.result()):
                return  # Hyprland quit
            await asyncio.to_thread(_move, raw.decode(errors="replace").strip(), env)
    finally:
        stopped.cancel()
