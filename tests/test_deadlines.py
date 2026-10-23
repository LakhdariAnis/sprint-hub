from datetime import date
from pathlib import Path

from hubd.model import Deadline
from hubd.vault import FileError, load_deadlines, load_vault

LINES = """# Deadlines

- [ ] 2026-11-05 PFE report draft #school [[sprint-hub v2/301]]
- [x] 2026-10-20 Fraunhofer IPA application #internship #de
- 2026-11-10 Compilation TP report
- [ ] 2026-13-01 Bad month #school
- [ ] soon Write the thing
- 2026-11-12 #school
"""


def test_load_deadlines(tmp_path: Path) -> None:
    path = tmp_path / "deadlines.md"
    path.write_text(LINES)
    deadlines, errors = load_deadlines(path)
    assert deadlines == [
        Deadline(
            date=date(2026, 11, 5),
            text="PFE report draft",
            tags=["school"],
            link="sprint-hub v2/301",
        ),
        Deadline(
            date=date(2026, 10, 20),
            text="Fraunhofer IPA application",
            done=True,
            tags=["internship", "de"],
        ),
        Deadline(date=date(2026, 11, 10), text="Compilation TP report"),  # no tags, no box
    ]
    assert errors == [
        FileError(path, 6, "bad date '2026-13-01', use YYYY-MM-DD"),
        FileError(path, 7, "bad date 'soon', use YYYY-MM-DD"),
        FileError(path, 8, "no text after the date"),
    ]


def test_no_deadlines_file(tmp_path: Path) -> None:
    assert load_deadlines(tmp_path / "deadlines.md") == ([], [])


def test_vault_keeps_deadlines_and_errors(vault: Path) -> None:
    (vault / "deadlines.md").write_text("- 2026-11-03 Apply #internship\n- tomorrow Oops\n")
    index = load_vault(vault)
    assert [d.text for d in index.deadlines] == ["Apply"]
    assert (vault / "deadlines.md", 2) in [(e.path, e.line) for e in index.errors]
