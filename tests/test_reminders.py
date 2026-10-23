import asyncio
from datetime import datetime
from pathlib import Path

import pytest
from conftest import Recorder

from hubd.daemon import Hub
from hubd.reminders import check, loop
from hubd.runners.fake import FakeRunner


def at(day: int, hour: int = 10) -> datetime:
    return datetime(2030, 1, day, hour)


@pytest.fixture
def remind(vault: Path, notifier: Recorder, tmp_path: Path):
    """`remind(lines, now)` restarts hubd on `lines` of deadlines.md and runs one check."""

    def run(lines: str, now: datetime) -> list[tuple[str, str]]:
        (vault / "deadlines.md").write_text(lines)
        hub = Hub(vault, lambda ended: FakeRunner(ended, delay=0), notifier)
        before = len(notifier.sent)
        check(hub, tmp_path / "state" / "reminders.json", 9, now)
        return notifier.sent[before:]

    return run


def test_3_1_0_days_before(remind) -> None:
    line = "- [ ] 2030-01-10 Thesis\n"
    assert remind(line, at(6)) == []
    assert remind(line, at(7)) == [("Deadline in 3 days", "Thesis")]
    assert remind(line, at(8)) == []  # the 3-day one is sent, 1-day not due yet
    assert remind(line, at(9)) == [("Deadline tomorrow", "Thesis")]
    assert remind(line, at(10)) == [("Deadline today", "Thesis")]
    assert remind(line, at(11)) == []  # overdue: no reminder


def test_no_repeat_after_restart(remind) -> None:
    line = "- [ ] 2030-01-10 Thesis\n"
    assert remind(line, at(10)) == [("Deadline today", "Thesis")]
    assert remind(line, at(10, 18)) == []


def test_catch_up_sends_only_the_most_urgent(remind) -> None:
    # hubd was off from day 6 to day 10: one "today", not three
    assert remind("- [ ] 2030-01-10 Thesis\n", at(10)) == [("Deadline today", "Thesis")]


def test_not_before_reminder_hour(remind) -> None:
    assert remind("- [ ] 2030-01-10 Thesis\n", at(10, 8)) == []
    assert remind("- [ ] 2030-01-10 Thesis\n", at(10, 9)) == [("Deadline today", "Thesis")]


def test_done_deadline_sends_nothing(remind) -> None:
    assert remind("- [x] 2030-01-10 Thesis\n", at(10)) == []


def test_moved_date_is_a_new_deadline(remind) -> None:
    assert remind("- [ ] 2030-01-10 Thesis\n", at(10)) == [("Deadline today", "Thesis")]
    assert remind("- [ ] 2030-01-12 Thesis\n", at(11)) == [("Deadline tomorrow", "Thesis")]


def test_linked_deadline_names_the_step(remind) -> None:
    sent = remind("- [ ] 2030-01-10 Ship [[demo/104]]\n", at(10))
    assert sent == [("Deadline today", "Ship (demo/104)")]


def test_broken_state_file_is_treated_as_empty(remind, tmp_path: Path) -> None:
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "reminders.json").write_text("{oops")
    assert remind("- [ ] 2030-01-10 Thesis\n", at(10)) == [("Deadline today", "Thesis")]


def test_loop_checks_at_start_and_stops(vault: Path, notifier: Recorder, tmp_path: Path) -> None:
    (vault / "deadlines.md").write_text("- [ ] 2030-01-10 Thesis\n")
    hub = Hub(vault, lambda ended: FakeRunner(ended, delay=0), notifier)

    async def main() -> None:
        stop = asyncio.Event()
        task = asyncio.create_task(loop(hub, tmp_path / "r.json", 9, stop, clock=lambda: at(10)))
        await asyncio.sleep(0.05)
        stop.set()
        await asyncio.wait_for(task, 1)

    asyncio.run(main())
    assert notifier.sent == [("Deadline today", "Thesis")]
