"""`hubd doctor`: check the Claude Code setup hubd depends on. One ✔/✘ line per check."""

import json
import shutil
import subprocess
from pathlib import Path

from hubd import install
from hubd.runners import claude


def _run(*argv: str) -> str:
    return subprocess.run(argv, capture_output=True, text=True, timeout=10, check=True).stdout


def checks(settings: Path = install.SETTINGS) -> list[tuple[bool, str]]:
    exe = shutil.which("claude")
    if exe is None:
        return [(False, "claude not on PATH"), *_hook(settings)]
    results = [(True, f"claude at {exe}")]
    try:
        results.append((True, f"version {_run(exe, '--version').strip()}"))
        help_text = _run(exe, "--help")
    except (OSError, subprocess.SubprocessError) as exc:
        return [*results, (False, f"claude does not run: {exc}"), *_hook(settings)]
    for flag in (claude.MODEL, claude.SESSION_ID, claude.RESUME):
        found = flag in help_text.split()
        results.append((found, f"flag {flag} {'in' if found else 'missing from'} claude --help"))
    return [*results, *_hook(settings)]


def _hook(settings: Path) -> list[tuple[bool, str]]:
    try:
        data = json.loads(settings.read_text()) if settings.exists() else {}
    except (OSError, ValueError) as exc:
        return [(False, f"cannot read {settings}: {exc}")]
    groups = data.get("hooks", {}).get(install.EVENT, [])
    commands = [h.get("command") for g in groups for h in g.get("hooks", []) if install.is_ours(h)]
    if install.COMMAND in commands:
        return [(True, f"{install.EVENT} hook installed")]
    if commands:
        return [(False, f"{install.EVENT} hook points to another python: run hubd install-hook")]
    return [(False, f"{install.EVENT} hook missing: run hubd install-hook")]


def main(settings: Path = install.SETTINGS) -> int:
    results = checks(settings)
    for ok, text in results:
        print(f"{'✔' if ok else '✘'} {text}")
    return 0 if all(ok for ok, _ in results) else 1
