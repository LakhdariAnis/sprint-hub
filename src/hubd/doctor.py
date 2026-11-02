"""`hubd doctor`: check the Claude Code setup and theme hubd depends on. One ✔/✘ line per check."""

import shutil
import subprocess
from pathlib import Path

from hubd import install, theme
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
    problem = install.hook_problem(settings)
    return [(False, problem)] if problem else [(True, f"{install.EVENT} hook installed")]


def _theme(path: Path) -> tuple[bool, str]:
    if path.is_file():
        return True, f"theme at {path}"
    return False, f"theme {path} not found: the app uses its default colours"


def main(settings: Path = install.SETTINGS, theme_file: Path = theme.OMARCHY) -> int:
    results = [*checks(settings), _theme(theme_file)]
    for ok, text in results:
        print(f"{'✔' if ok else '✘'} {text}")
    return 0 if all(ok for ok, _ in results) else 1
