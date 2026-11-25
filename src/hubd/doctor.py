"""`hubd doctor`: check the Claude Code setup and theme hubd depends on. One ✔/✘ line per check."""

import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

from hubd import install, service, theme
from hubd.model import State
from hubd.runners import claude
from hubd.settings import load_settings
from hubd.vault import load_vault, vault_path

WARNING = "warning:"  # a line that is not a failure, but is not fine either


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
    problems = [(event, install.hook_problem(settings, event)) for event in install.EVENTS]
    if (first := problems[0][1]) and first.startswith("cannot read"):
        return [(False, first)]  # one unreadable file, one line
    return [(not p, p or f"{event} hook installed") for event, p in problems]


def _theme(path: Path) -> tuple[bool, str]:
    if path.is_file():
        return True, f"theme at {path}"
    return False, f"theme {path} not found: the app uses its default colours"


def _graphify() -> tuple[bool, str]:
    """Not a failure when missing: the code graph is opt-in per project (ADR 0004)."""
    exe = shutil.which("graphify")
    if exe is None:
        return True, f"{WARNING} graphify not on PATH: project graphs cannot be built"
    try:
        return True, f"{_run(exe, '--version').strip()} at {exe}"
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"graphify does not run: {exc}"


def _terminal(vault: Path) -> tuple[bool, str]:
    try:
        exe = load_settings(vault / "hub.toml").terminal[0]
    except (OSError, ValueError, IndexError) as exc:
        return False, f"cannot read the terminal from {vault / 'hub.toml'}: {exc}"
    found = shutil.which(exe)
    return (True, f"terminal at {found}") if found else (False, f"terminal {exe} not on PATH")


def _commands(vault: Path) -> list[tuple[bool, str]]:
    """Per project: every todo step needs its command, or its start is refused."""
    index = load_vault(vault)
    results = []
    for name, project in index.projects.items():
        todo = [
            e.step.step
            for e in index.steps
            if e.project == name and e.step.state == State.todo and e.step.by == "claude"
        ]
        commands = vault / project.repo / ".claude" / "commands" if project.repo else None
        if not todo or commands is None:
            continue
        missing = [s for s in todo if not (commands / f"sprint-{s}.md").is_file()]
        if missing:
            results.append((False, f"{name}: no command in {commands} for {', '.join(missing)}"))
        else:
            results.append((True, f"{name}: command for each of {len(todo)} todo steps"))
    return results


def _workspaces(vault: Path) -> list[tuple[bool, str]]:
    """Per project with a workspace: `hyprctl` found or not. A shared number warns."""
    projects = {n: p.workspace for n, p in load_vault(vault).projects.items() if p.workspace}
    hypr = shutil.which("hyprctl") is not None
    results = [
        (True, f"{name}: runs open on workspace {n}")
        if hypr
        else (
            False,
            f"{name}: workspace {n} needs hyprctl on PATH (Hyprland); its runs open anywhere",
        )
        for name, n in projects.items()
    ]
    for n in sorted(set(projects.values())):
        names = [name for name, w in projects.items() if w == n]
        if len(names) > 1:  # not a failure: the windows just tile together
            results.append((True, f"{WARNING} workspace {n} is shared by {', '.join(names)}"))
    return results


def fix_for(text: str) -> str | None:
    """The command that fixes a failed line, when there is one."""
    return "uv run hubd install-hook" if "run hubd install-hook" in text else None


def report(
    vault: Path, settings: Path = install.SETTINGS, theme_file: Path = theme.OMARCHY
) -> list[dict]:
    """Every check as `{ok, text, fix}`; `hubd doctor` and `GET /doctor` share it."""
    results = [
        *checks(settings),
        _theme(theme_file),
        _graphify(),
        _terminal(vault),
        *_commands(vault),
        *_workspaces(vault),
    ]
    return [{"ok": ok, "text": text, "fix": None if ok else fix_for(text)} for ok, text in results]


def main(
    settings: Path = install.SETTINGS,
    theme_file: Path = theme.OMARCHY,
    service_state: Callable[[], str] | None = None,
) -> int:
    results = report(vault_path(), settings, theme_file)
    for r in results:
        mark = "⚠" if r["text"].startswith(WARNING) else "✔" if r["ok"] else "✘"
        print(f"{mark} {r['text']}")
    # Info, not a check: hubd also runs without the service (bin/sprint-hub-app starts it).
    print(f"ℹ hubd service: {(service_state or service.state)()}")
    return 0 if all(r["ok"] for r in results) else 1
