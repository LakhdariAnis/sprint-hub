"""The desktop session's environment, for the programs hubd starts (notify-send, the terminal)."""

import os
import subprocess

# systemd starts hubd at login, before the compositor exists. Once it runs, the user manager
# holds WAYLAND_DISPLAY, HYPRLAND_INSTANCE_SIGNATURE and the rest (uwsm exports them there).
_MARKER = "WAYLAND_DISPLAY"


def env() -> dict[str, str]:
    """`os.environ`, plus what the user manager knows and this process lacks."""
    merged = dict(os.environ)
    if _MARKER in merged:
        return merged
    try:
        shown = subprocess.run(
            ["systemctl", "--user", "show-environment"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return merged  # no systemd: nothing more to learn
    for line in shown.splitlines():
        key, sep, value = line.partition("=")
        if sep and key not in merged:
            merged[key] = value
    return merged
