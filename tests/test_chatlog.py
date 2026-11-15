"""The vault's chats.md: write, read, rename, a broken entry."""

from datetime import datetime
from pathlib import Path

from hubd import chatlog
from hubd.chatlog import ChatEntry

NOW = datetime(2026, 11, 11, 14, 36, 5)
A = "0b1e5b7e-5b0c-4d57-9a54-1a5c8a2f0001"
B = "0b1e5b7e-5b0c-4d57-9a54-1a5c8a2f0002"


def entry(id: str = A, **kw: object) -> ChatEntry:
    base = {"title": "Plan the week", "model": "sonnet", "effort": "medium", "kind": "none"}
    return ChatEntry(id=id, created=NOW, used=NOW, **(base | kw))  # type: ignore[arg-type]


def test_path_of(tmp_path: Path) -> None:
    assert chatlog.path_of(tmp_path, "ros2_car") == tmp_path / "projects/ros2_car/chats.md"
    assert chatlog.path_of(tmp_path, None) == tmp_path / "chats/scratch.md"


def test_write_then_read(tmp_path: Path) -> None:
    path = tmp_path / "projects/p/chats.md"  # the folder is made
    full = entry(B, kind="step", sprint=6, step="609", open=False, title="Why · the | SSE drops?")
    chatlog.save(path, entry())
    chatlog.save(path, full)
    assert chatlog.load(path) == [entry(), full]
    assert "- title: Plan the week" in path.read_text()


def test_save_replaces_the_entry_with_the_same_id(tmp_path: Path) -> None:
    path = tmp_path / "chats.md"
    chatlog.save(path, entry())
    chatlog.save(path, entry(B))
    chatlog.save(path, entry(title="Other"))
    assert [(e.id, e.title) for e in chatlog.load(path)] == [(A, "Other"), (B, "Plan the week")]


def test_rename_and_close_keep_the_rest(tmp_path: Path) -> None:
    path = tmp_path / "chats.md"
    chatlog.save(path, entry(kind="project"))
    chatlog.save(path, entry(B))
    renamed = chatlog.change(path, A, title="Sidebar work", open=False)
    assert renamed and renamed.title == "Sidebar work" and not renamed.open
    assert chatlog.load(path) == [renamed, entry(B)]
    assert chatlog.change(path, "nope", title="x") is None


def test_missing_file_and_broken_entry(tmp_path: Path) -> None:
    assert chatlog.load(tmp_path / "none.md") == []
    path = tmp_path / "chats.md"
    chatlog.save(path, entry())
    path.write_text(path.read_text() + "\n## broken\n- title: no model\n- created: yesterday\n")
    assert [e.id for e in chatlog.load(path)] == [A]  # the good one survives


def test_title_is_the_first_message_cut_to_40() -> None:
    assert chatlog.title_of("  hello\n  there ") == "hello there"
    long = chatlog.title_of("x" * 100)
    assert len(long) == chatlog.TITLE and long.endswith("…")
    assert chatlog.title_of("y" * 40) == "y" * 40
