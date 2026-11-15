"""The session-file reader: a fixture shaped like Claude's file, and files that are not."""

from pathlib import Path

from hubd.transcript import read_claude

FIXTURE = Path(__file__).parent / "fixtures" / "session" / "chat.jsonl"
ID = "5f0e4c1a-0000-4000-8000-000000000001"


def folder(tmp_path: Path, text: str) -> Path:
    (tmp_path / "-work-repo").mkdir()
    (tmp_path / "-work-repo" / f"{ID}.jsonl").write_text(text)
    return tmp_path


def test_fixture_gives_the_turns_in_order(tmp_path: Path) -> None:
    turns = read_claude(ID, folder(tmp_path, FIXTURE.read_text()))
    assert turns is not None
    assert [t["text"] for t in turns] == ["what files are here?", "what did I ask first?"]
    assert all(t["done"] for t in turns)
    first = turns[0]["events"]
    assert [e["kind"] for e in first] == ["text", "tool", "tool_result", "text"]
    assert first[1]["line"] == "Read README.md"  # relative to the chat's cwd
    assert first[2] == {
        "kind": "tool_result",
        "tool_id": "toolu_1",
        "text": "# Repo\nhello",
        "error": False,
    }
    assert first[3]["text"] == "One file: README.md. It says hello."  # blocks joined
    assert turns[1]["events"] == [{"kind": "text", "text": "You asked what files are here."}]


def test_no_file_or_no_folder(tmp_path: Path) -> None:
    assert read_claude(ID, tmp_path) is None
    assert read_claude(ID, tmp_path / "missing") is None


def test_broken_file_gives_none_not_a_crash(tmp_path: Path) -> None:
    for text in (
        "",
        "\x00\x01 not json\n{",
        '{"type":"user"}\n[1,2]\n"x"\n',
        '{"type":"user","message":{"content":5}}',
    ):
        assert read_claude(ID, folder(tmp_path, text)) is None
        (tmp_path / "-work-repo" / f"{ID}.jsonl").unlink()
        (tmp_path / "-work-repo").rmdir()


def test_one_bad_line_keeps_the_rest(tmp_path: Path) -> None:
    lines = FIXTURE.read_text().splitlines()
    turns = read_claude(ID, folder(tmp_path, "\n".join(lines[:2] + ["{"] + lines[2:])))
    assert turns and len(turns) == 2
