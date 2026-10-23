"""Deadline reminders: 3 days before, 1 day before and on the day, each one once."""

import asyncio
import json
import os
from collections.abc import Callable
from contextlib import suppress
from datetime import datetime
from pathlib import Path

from hubd.daemon import Hub

KINDS = (0, 1, 3)  # days left at which a reminder is due, most urgent first
EVERY = 300  # seconds between checks


def state_path() -> Path:
    return Path.home() / ".local" / "state" / "sprint-hub" / "reminders.json"


def check(hub: Hub, path: Path, hour: int, now: datetime) -> None:
    """Send the most urgent due reminder of each open deadline, unless it was sent before."""
    if now.hour < hour:
        return
    today = now.date()
    sent = _load(path)
    new = []
    for deadline in hub.deadlines(max(KINDS), today):
        left = (deadline.date - today).days
        if left < 0:
            continue  # overdue: Today shows it in red, no reminder
        kind = next(k for k in KINDS if k >= left)
        # The date is in the key, so a moved deadline is a new one.
        key = f"{deadline.date} {kind} {deadline.text}"
        if key in sent:
            continue
        when = {0: "today", 1: "tomorrow"}.get(left, f"in {left} days")
        body = f"{deadline.text} ({deadline.link})" if deadline.link else deadline.text
        hub.notifier.notify(f"Deadline {when}", body)
        new.append(key)
    if new:
        # shortcut: old keys are never pruned; a few lines per deadline, fine for years.
        _save(path, sorted({*sent, *new}))


async def loop(
    hub: Hub,
    path: Path,
    hour: int,
    stop: asyncio.Event,
    clock: Callable[[], datetime] = datetime.now,
) -> None:
    """Check at start, then every `EVERY` seconds, until `stop`."""
    while not stop.is_set():
        check(hub, path, hour, clock())
        with suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), EVERY)


def _load(path: Path) -> set[str]:
    try:
        return set(json.loads(path.read_text()))
    except (OSError, ValueError):
        return set()  # no or broken file: at worst a reminder comes twice


def _save(path: Path, keys: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(keys, indent=1) + "\n")
    os.replace(tmp, path)
