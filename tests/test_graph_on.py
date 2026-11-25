"""Step 655: `graph: on` per project, and the builds that keep it fresh."""

from pathlib import Path

from hubd.vault import _load_project, save_graph

PROJECT = "---\r\nname: p\r\nmodel: sonnet  # kept\r\nmerge: manual\r\n---\r\nbody\r\n"


def test_graph_line_comes_and_goes_byte_safe(tmp_path: Path) -> None:
    path = tmp_path / "project.md"
    path.write_bytes(PROJECT.encode())
    assert _load_project(path).graph is False
    save_graph(path, True)
    assert b"graph: on\r\n" in path.read_bytes()
    assert _load_project(path).graph is True
    save_graph(path, True)
    assert path.read_bytes().count(b"graph:") == 1
    save_graph(path, False)
    assert path.read_bytes() == PROJECT.encode()
