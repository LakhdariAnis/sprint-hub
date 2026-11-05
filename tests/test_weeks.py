from pathlib import Path

from hubd.weeks import parse_sprints

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
