"""`hubd install-hook` / `uninstall-hook`: the SessionEnd hook in Claude's settings."""

import difflib
import json
import shlex
import sys
from collections.abc import Callable
from pathlib import Path

from hubd.vault import _write_atomic

SETTINGS = Path.home() / ".claude" / "settings.json"
EVENT = "SessionEnd"
# shortcut: pins the hook to this venv's python, run install-hook again if the venv moves.
COMMAND = f"{shlex.quote(sys.executable)} -m hubd.hook"


def is_ours(handler: dict) -> bool:
    return str(handler.get("command", "")).endswith("-m hubd.hook")


def installed(settings: dict) -> bool:
    groups = settings.get("hooks", {}).get(EVENT, [])
    return any(is_ours(h) for g in groups for h in g.get("hooks", []))


def hook_problem(path: Path = SETTINGS) -> str | None:
    """Why this hubd will not hear a run end; None when the hook is installed with this python."""
    try:
        data = json.loads(path.read_text()) if path.exists() else {}
    except (OSError, ValueError) as exc:
        return f"cannot read {path}: {exc}"
    groups = data.get("hooks", {}).get(EVENT, [])
    commands = [h.get("command") for g in groups for h in g.get("hooks", []) if is_ours(h)]
    if COMMAND in commands:
        return None
    if commands:
        return f"{EVENT} hook points to another python: run hubd install-hook"
    return f"{EVENT} hook missing: run hubd install-hook"


def with_hook(settings: dict) -> dict:
    new = uninstalled(settings)  # replaces an old entry, e.g. from another venv
    group = {"hooks": [{"type": "command", "command": COMMAND}]}
    new.setdefault("hooks", {}).setdefault(EVENT, []).append(group)
    return new


def uninstalled(settings: dict) -> dict:
    new = json.loads(json.dumps(settings))
    hooks = new.get("hooks", {})
    groups = []
    for group in hooks.get(EVENT, []):
        group["hooks"] = [h for h in group.get("hooks", []) if not is_ours(h)]
        if group["hooks"]:
            groups.append(group)
    if groups:
        hooks[EVENT] = groups
    else:
        hooks.pop(EVENT, None)
    if "hooks" in new and not hooks:
        del new["hooks"]
    return new


def confirm_write(path: Path, old: str, new: str, ask: Callable[[str], str] = input) -> bool:
    """Show the diff of `path`, ask y/N."""
    sys.stdout.writelines(
        difflib.unified_diff(
            old.splitlines(keepends=True), new.splitlines(keepends=True), str(path), str(path)
        )
    )
    try:
        answer = ask(f"Write {path}? [y/N] ")
    except EOFError:  # no terminal to ask: treat as no
        answer = ""
    if answer.strip().lower() != "y":
        print("nothing written")
        return False
    return True


def change(
    edit: Callable[[dict], dict],
    path: Path = SETTINGS,
    ask: Callable[[str], str] = input,
) -> int:
    """Show the diff of `path`, ask, then write. Nothing to change = nothing asked."""
    text = path.read_text() if path.exists() else "{}\n"
    old = json.loads(text)
    new = edit(old)
    if new == old:
        print(f"{path}: already up to date")
        return 0
    new_text = json.dumps(new, indent=2) + "\n"
    if not confirm_write(path, text, new_text, ask):
        return 1
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("{}\n")  # _write_atomic copies the mode of an existing file
    _write_atomic(path, new_text.encode())
    print(f"{path}: written")
    return 0
