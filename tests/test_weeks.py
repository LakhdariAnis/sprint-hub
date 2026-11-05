from datetime import date
from pathlib import Path

from hubd.weeks import Sprint, calibration, eta, parse_sprints, sunday_of, week_of, week_view

README = (Path(__file__).parent / "fixtures" / "sprints" / "README.md").read_text()


def test_parse_fixture() -> None:
    sprints, warnings = parse_sprints("p", README)
    assert [s.number for s in sprints] == [1, 2, 3, 4, 5, 6]
    s1, s2, s3, _, _, s6 = sprints
    assert (s1.track, s1.week, s1.planned, s1.actual, s1.status) == (
        "personal",
        "2026-W43",
        13.5,
        5.75,
        "closed",
    )
    assert (s2.planned, s2.actual) == (20, None)  # "Anis not recorded" is not an actual
    assert (s3.planned, s3.actual) == (None, None)
    assert (s6.track, s6.week) == (None, None)
    lines = [n for n, _ in warnings]
    assert lines == [21, 22, 23, 24, 25, 26]
    assert "1 cells" in warnings[0][1]
    assert "track 'weekend'" in warnings[1][1]
    assert "week '2026-W54'" in warnings[2][1]
    assert "status 'someday'" in warnings[3][1]
    assert "planned 'lots'" in warnings[4][1]
    assert "'ten'" in warnings[5][1]


def test_no_table_is_a_warning_not_a_crash() -> None:
    for text in ("", "# Title\n\nNo sprints here.\n", "## Sprints\n\nNothing yet.\n"):
        assert parse_sprints("p", text)[0] == []
        assert len(parse_sprints("p", text)[1]) == 1


def test_missing_column() -> None:
    sprints, warnings = parse_sprints(
        "p", "## Sprints\n\n| Sprint | Goal |\n|---|---|\n| 1 | x |\n"
    )
    assert sprints == []
    assert "lacks column track, week, planned, status" in warnings[0][1]


def test_week_edges() -> None:
    assert week_of(date(2026, 11, 2)) == "2026-W45"  # Monday
    assert week_of(date(2026, 11, 8)) == "2026-W45"  # Sunday
    assert week_of(date(2026, 11, 9)) == "2026-W46"
    assert week_of(date(2026, 12, 31)) == "2026-W53"  # the year changes inside a week
    assert week_of(date(2027, 1, 3)) == "2026-W53"
    assert week_of(date(2025, 12, 29)) == "2026-W01"
    assert sunday_of("2026-W53") == date(2027, 1, 3)


def sprint(n: int, track: str, week: str, status: str = "current", **kw) -> Sprint:
    base = dict(
        project="a",
        number=n,
        track=track,
        week=week,
        goal=f"goal {n}",
        planned=10.0,
        actual=None,
        status=status,
    )
    return Sprint(**{**base, **kw})


def view(tables: dict[str, list[Sprint]], today: date) -> dict:
    return week_view(tables, [], {"a": "A", "b": "B"}, today)


def test_week_view_days_left() -> None:
    tables = {"a": [sprint(1, "work", "2026-W45")]}
    assert view(tables, date(2026, 11, 2))["days_left"] == 7  # Monday
    assert view(tables, date(2026, 11, 8))["days_left"] == 1  # Sunday
    assert view(tables, date(2026, 11, 8))["sunday"] == "2026-11-08"
    assert view(tables, date(2026, 11, 8))["monday"] == "2026-11-02"
    assert view(tables, date(2026, 12, 31))["days_left"] == 4  # W53 ends Sunday 2027-01-03
    assert view(tables, date(2026, 12, 31))["week"] == "2026-W53"


def test_week_view_lists_the_tracks() -> None:
    tables = {
        "a": [
            sprint(1, "work", "2026-W45"),
            sprint(2, "work", "2026-W46"),
            sprint(3, "work", "2026-W45", "moved"),
        ],
        "b": [sprint(7, "personal", "2026-W45", project="b")],
    }
    v = view(tables, date(2026, 11, 5))
    assert [r["sprint"] for r in v["tracks"]["work"]] == [1]
    assert [(r["name"], r["goal"]) for r in v["tracks"]["personal"]] == [("B", "goal 7")]
    assert v["warnings"] == []


def test_warn_two_in_one_track() -> None:
    tables = {"a": [sprint(1, "work", "2026-W45"), sprint(2, "work", "2026-W45")]}
    assert view(tables, date(2026, 11, 5))["warnings"] == [
        "2 work sprints in 2026-W45 (A 1, A 2). One per track."
    ]


def test_warn_no_work_sprint() -> None:
    tables = {"a": [sprint(1, "personal", "2026-W45")]}
    assert view(tables, date(2026, 11, 5))["warnings"] == ["No work sprint in 2026-W45."]
    assert view({}, date(2026, 11, 5))["warnings"] == [
        "No work sprint in 2026-W45."
    ]  # no personal warning


def test_calibration_without_data() -> None:
    assert calibration("a", {}) == (1.0, 0, "none")
    # Closed with "not recorded" hours does not count.
    assert calibration("a", {"a": [sprint(1, "work", "2026-W43", "closed")]}) == (1.0, 0, "none")


def test_calibration_last_three_closed() -> None:
    closed = [
        sprint(n, "work", f"2026-W4{n}", "closed", planned=10.0, actual=a)
        for n, a in ((1, 100.0), (2, 5.0), (3, 10.0), (4, 15.0))
    ]
    factor, used, source = calibration("a", {"a": closed})
    assert (factor, used, source) == (
        1.0,
        3,
        "project",
    )  # sprint 1 (100 h) is older than the last 3


def test_calibration_falls_back_on_the_track() -> None:
    tables = {
        "a": [sprint(1, "work", "2026-W45", "planned")],
        "b": [sprint(1, "work", "2026-W43", "closed", project="b", planned=10.0, actual=5.0)],
    }
    assert calibration("a", tables) == (0.5, 1, "track")


def test_eta() -> None:
    tables = {
        "a": [
            sprint(1, "work", "2026-W43", "closed", planned=10.0, actual=5.0),
            sprint(2, "work", "2026-W44", "current"),  # late: its week is over
            sprint(3, "work", "2026-W46", "planned", planned=14.0),
            sprint(4, "work", "2026-W48", "planned", planned=6.0),
            sprint(5, "work", None, "planned", planned=None),
        ]
    }
    e = eta("a", tables, [], date(2026, 11, 5))
    assert (e["sprints"], e["raw_hours"], e["factor"], e["hours"]) == (4, 30.0, 0.5, 15.0)
    assert (e["week"], e["sunday"]) == ("2026-W48", "2026-11-29")
    assert [(f["sprint"], f["kind"]) for f in e["flags"]] == [(2, "overdue")]


def test_eta_flags_current_in_the_future_and_no_data() -> None:
    e = eta("a", {"a": [sprint(1, "work", "2026-W47")]}, [], date(2026, 11, 5))
    assert [f["kind"] for f in e["flags"]] == ["wrong_week"]
    assert (e["factor"], e["factor_from"]) == (1.0, "none")
    none = eta("a", {}, [], date(2026, 11, 5))
    assert none["data"] is False
    assert none["week"] is None
