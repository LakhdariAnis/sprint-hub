"""`hubd install-service` / `uninstall-service`: hubd as a systemd user service."""

import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from hubd import install

UNIT = Path.home() / ".config" / "systemd" / "user" / "hubd.service"
NAME = "hubd.service"
REPO = Path(__file__).resolve().parents[2]
PORT_BUSY = 98  # exit code of hubd when its port is taken; the unit does not restart on it


def unit_text(exe: Path, path_env: str) -> str:
    # PATH is fixed here because a service does not get the shell's (mise puts `claude` there).
    # WAYLAND_DISPLAY and friends are read from the user manager at spawn (hubd.session).
    # `%` is a specifier in unit files; `"` ends the value.
    path_env = path_env.replace("%", "%%").replace('"', "")
    return f"""[Unit]
Description=sprint-hub daemon

[Service]
ExecStart={exe}
Environment="PATH={path_env}"
Restart=on-failure
RestartSec=2
RestartPreventExitStatus={PORT_BUSY}

[Install]
WantedBy=default.target
"""


def systemctl(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["systemctl", "--user", *args], capture_output=True, text=True)


def state(run: Callable[..., subprocess.CompletedProcess[str]] = systemctl) -> str:
    """`not installed`, or what `systemctl is-active` says (active, inactive, failed, ...)."""
    if not UNIT.exists():
        return "not installed"
    try:
        return run("is-active", NAME).stdout.strip() or "unknown"
    except OSError:
        return "unknown (no systemctl)"


def _run(run: Callable[..., subprocess.CompletedProcess[str]], *args: str) -> bool:
    result = run(*args)
    if result.returncode:
        print(f"systemctl --user {' '.join(args)}: {result.stderr.strip()}", file=sys.stderr)
    return result.returncode == 0


def install_service(
    unit: Path = UNIT,
    exe: Path = REPO / ".venv" / "bin" / "hubd",
    path_env: str | None = None,
    ask: Callable[[str], str] = input,
    run: Callable[..., subprocess.CompletedProcess[str]] = systemctl,
) -> int:
    if not exe.exists():
        print(f"{exe} not found: run uv sync", file=sys.stderr)
        return 1
    new = unit_text(exe, os.environ["PATH"] if path_env is None else path_env)
    old = unit.read_text() if unit.exists() else ""
    if new != old:
        if not install.confirm_write(unit, old, new, ask):
            return 1
        unit.parent.mkdir(parents=True, exist_ok=True)
        unit.write_text(new)
        print(f"{unit}: written")
    else:
        print(f"{unit}: already up to date")
    ok = _run(run, "daemon-reload") and _run(run, "enable", "--now", NAME)
    return 0 if ok else 1


def uninstall_service(
    unit: Path = UNIT,
    ask: Callable[[str], str] = input,
    run: Callable[..., subprocess.CompletedProcess[str]] = systemctl,
) -> int:
    if not unit.exists():
        print(f"{unit}: not installed")
        return 0
    if not install.confirm_write(unit, unit.read_text(), "", ask):
        return 1
    _run(run, "disable", "--now", NAME)  # best effort: the file goes either way
    unit.unlink()
    print(f"{unit}: removed")
    return 0 if _run(run, "daemon-reload") else 1
