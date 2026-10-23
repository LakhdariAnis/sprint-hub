from datetime import date, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from hubd.api import create_app
from hubd.daemon import Hub
from hubd.model import Deadline
from hubd.notify import NullNotifier
from hubd.runners.fake import FakeRunner
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


def test_hub_deadlines_window_and_steps(vault: Path) -> None:
    (vault / "deadlines.md").write_text(
        "- 2026-10-20 Overdue thing\n"
        "- [x] 2026-10-21 Done thing\n"
        "- 2026-10-30 In a week\n"
        "- 2026-10-31 Too far\n"
    )
    approved = vault / "projects" / "demo" / "steps" / "105.md"
    approved.write_text(
        approved.read_text().replace("state: approved", "state: approved\ndue: 2026-10-25")
    )
    hub = Hub(vault, lambda ended: FakeRunner(ended, delay=0), NullNotifier())
    got = hub.deadlines(7, today=date(2026, 10, 23))
    # Step 102 (doing) has `due: 2026-10-24`; approved 105 is left out.
    assert [(d.date.isoformat(), d.text, d.link) for d in got] == [
        ("2026-10-20", "Overdue thing", None),
        ("2026-10-24", "Serve the API", "demo/102"),
        ("2026-10-30", "In a week", None),
    ]


def test_get_deadlines(vault: Path) -> None:
    today = date.today()
    (vault / "deadlines.md").write_text(
        f"- [ ] {today - timedelta(days=1)} Late #school\n"
        f"- [ ] {today} Today\n"
        f"- [ ] {today + timedelta(days=3)} Soon [[demo/101]]\n"
    )
    client = TestClient(create_app(Hub(vault, lambda e: FakeRunner(e), NullNotifier())))
    items = client.get("/deadlines?days=3").json()
    files = [i for i in items if i["link"] != "demo/102"]  # the fixture step's own `due:`
    assert files == [
        {
            "date": str(today - timedelta(days=1)),
            "text": "Late",
            "done": False,
            "tags": ["school"],
            "link": None,
            "overdue": True,
        },
        {
            "date": str(today),
            "text": "Today",
            "done": False,
            "tags": [],
            "link": None,
            "overdue": False,
        },
        {
            "date": str(today + timedelta(days=3)),
            "text": "Soon",
            "done": False,
            "tags": [],
            "link": "demo/101",
            "overdue": False,
        },
    ]
    assert [i["date"] for i in items] == sorted(i["date"] for i in items)
    assert client.get("/deadlines?days=-1").status_code == 422
