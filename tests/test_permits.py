"""The permission rules: scratch chats, "Allow for this chat", the card, the flags."""

from pathlib import Path

import pytest

from hubd import permits

UNSAFE = ("bypassPermissions", "acceptEdits", "auto", "dontAsk", "--dangerously-skip-permissions")


@pytest.mark.parametrize("scratch", [True, False])
def test_flags_never_skip_permissions(scratch: bool) -> None:
    args = permits.flags(scratch)
    assert args[:2] == ["--permission-mode", "default"]
    assert not any(bad in arg for arg in args for bad in UNSAFE)


def test_scratch_chat_does_not_get_commands() -> None:
    assert permits.flags(True)[2:] == ["--disallowedTools", "Bash,PowerShell"]
    assert permits.flags(False)[2:] == []


def test_scratch_chat_refuses_commands_and_files_outside(tmp_path: Path) -> None:
    def refuse(tool: str, given: dict) -> str | None:
        return permits.refuse(tool, given, tmp_path, scratch=True)

    assert refuse("Bash", {"command": "ls"})
    assert refuse("Edit", {"file_path": str(Path.home() / ".bashrc")})
    assert refuse("Write", {"file_path": "../escape.txt"})
    assert refuse("Write", {})  # no path: not inside
    assert refuse("Write", {"file_path": str(tmp_path / "a.txt")}) is None
    assert refuse("Write", {"file_path": "notes/a.txt"}) is None
    assert refuse("WebFetch", {"url": "https://example.com"}) is None  # Anis decides


def test_project_chat_lets_anis_decide(tmp_path: Path) -> None:
    assert permits.refuse("Bash", {"command": "rm -rf /"}, tmp_path, scratch=False) is None
    assert permits.refuse("Edit", {"file_path": "/etc/hosts"}, tmp_path, scratch=False) is None


def test_allow_for_chat_covers_files_only_inside(tmp_path: Path) -> None:
    assert permits.chat_wide("Bash", {"command": "ls"}, tmp_path)
    assert permits.chat_wide("Edit", {"file_path": "src/a.py"}, tmp_path)
    assert not permits.chat_wide("Edit", {"file_path": "/etc/hosts"}, tmp_path)
    assert not permits.chat_wide("Write", {}, tmp_path)


def test_card_shows_command_or_file_and_a_short_diff() -> None:
    assert permits.card("Bash", {"command": "ls -la"}) == {"target": "ls -la", "diff": None}
    edit = {"file_path": "a.py", "old_string": "x = 1", "new_string": "x = 2\ny = 3"}
    assert permits.card("Edit", edit) == {"target": "a.py", "diff": "- x = 1\n+ x = 2\n+ y = 3"}
    write = permits.card("Write", {"file_path": "b.txt", "content": "\n".join("abcdefghijklmnop")})
    assert write["target"] == "b.txt"
    assert write["diff"].splitlines()[-1] == "… 4 more lines"
    assert len(write["diff"].splitlines()) == permits.DIFF_LINES + 1
    assert permits.card("WebFetch", {"url": "https://x.org"}) == {
        "target": "https://x.org",
        "diff": None,
    }
