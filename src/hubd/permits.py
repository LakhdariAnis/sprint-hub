"""What a chat may do without Anis, and what his permission card shows (607). All rules live here.

Claude asks hubd through `--permission-prompt-tool` only for calls its permission mode would
prompt for: reads inside the chat's folder and the read-only commands never reach hubd.
https://code.claude.com/docs/en/cli-reference, https://code.claude.com/docs/en/headless
(checked 2026-11-11).
"""

import shlex
from pathlib import Path
from typing import Any

# `default` asks for every edit and command. Never `bypassPermissions`, `acceptEdits`, `auto` or
# `--dangerously-skip-permissions`: test_permits.py checks the flags.
MODE = "default"
COMMANDS = ("Bash", "PowerShell")  # tools that run code: never in a scratch chat
# `Edit(path)` rules cover every built-in tool that writes a file.
# https://code.claude.com/docs/en/agent-sdk/permissions#path-patterns-in-rules (checked 2026-11-11)
FILES = ("Edit", "Write", "MultiEdit", "NotebookEdit")
# graphify commands that only read a graph: a project chat runs them with no card (657).
GRAPH_READS = ("query", "path", "affected", "explain")
DIFF_LINES = 12  # lines of a card's diff
ASK_WAIT = 10 * 60  # seconds a card waits for Anis, then the call is denied


def flags(scratch: bool) -> list[str]:
    """Permission flags of a `claude -p` chat. A scratch chat does not even see the commands."""
    args = ["--permission-mode", MODE]
    return args + (["--disallowedTools", ",".join(COMMANDS)] if scratch else [])


def path_of(tool_input: dict[str, Any]) -> str | None:
    value = tool_input.get("file_path") or tool_input.get("notebook_path")
    return value if isinstance(value, str) else None


def inside(path: str, folder: Path) -> bool:
    target = (folder / Path(path).expanduser()).resolve()
    return target.is_relative_to(folder.resolve())


def refuse(tool: str, tool_input: dict[str, Any], cwd: Path, scratch: bool) -> str | None:
    """The deny message for a call no card may allow, else None (Anis decides)."""
    if not scratch:
        return None
    if tool in COMMANDS:
        return "A chat with no project never runs commands. Ask Anis to open it on a project."
    path = path_of(tool_input)
    if tool in FILES and (path is None or not inside(path, cwd)):
        return f"A chat with no project only writes inside {cwd}."
    return None


def graph_read(tool: str, tool_input: dict[str, Any], graph: Path | None) -> bool:
    """Is this Bash call one plain `graphify query|path|affected|explain … --graph <graph>`?

    Nothing the shell would read as more than one command, a redirect or an expansion passes.
    """
    command = tool_input.get("command")
    if tool != "Bash" or graph is None or not isinstance(command, str):
        return False
    if any(c in command for c in "$`\\\n\r"):
        return False
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        words = list(lexer)
    except ValueError:  # an open quote
        return False
    if any(w and set(w) <= set(lexer.punctuation_chars) for w in words):
        return False  # ; & | < > ( ) outside quotes
    if len(words) < 3 or words[0] != "graphify" or words[1] not in GRAPH_READS:
        return False
    given = [words[i + 1] for i, w in enumerate(words[:-1]) if w == "--graph"]
    if any(w.startswith("--graph=") for w in words) or words[-1] == "--graph":
        return False
    return given == [str(graph)]


def chat_wide(tool: str, tool_input: dict[str, Any], cwd: Path) -> bool:
    """Can "Allow for this chat" cover this call? File writes only inside the chat's folder."""
    path = path_of(tool_input)
    return tool not in FILES or (path is not None and inside(path, cwd))


def card(tool: str, tool_input: dict[str, Any]) -> dict[str, str | None]:
    """What the card shows: the command or file, and a short diff for a file write."""
    if isinstance(command := tool_input.get("command"), str):
        return {"target": command, "diff": None}
    if (path := path_of(tool_input)) is None:
        first = next((v for v in tool_input.values() if isinstance(v, str)), "")
        return {"target": first, "diff": None}
    edits = tool_input.get("edits") or [tool_input]  # MultiEdit holds a list of edits
    lines: list[str] = []
    for edit in edits:
        old, new = edit.get("old_string"), edit.get("new_string", edit.get("content"))
        lines += [f"- {line}" for line in (old or "").splitlines()]
        lines += [f"+ {line}" for line in (new or edit.get("new_source") or "").splitlines()]
    cut = len(lines) - DIFF_LINES
    lines = lines[:DIFF_LINES] + ([f"… {cut} more lines"] if cut > 0 else [])
    return {"target": path, "diff": "\n".join(lines) or None}


def short(tool: str, tool_input: dict[str, Any]) -> str:
    """The popup's line: the tool and the file's name, or the command's first 40 characters."""
    target = str(card(tool, tool_input)["target"] or "")
    target = Path(target).name if path_of(tool_input) else " ".join(target.split())[:40]
    return f"{tool}: {target}"
