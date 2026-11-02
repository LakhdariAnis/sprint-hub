"""Desktop notifications behind one interface (docs/ROADMAP.md rule 4)."""

import subprocess
from typing import Protocol

from hubd import session


class Notifier(Protocol):
    def notify(self, title: str, body: str) -> None: ...


class NotifySend:
    def notify(self, title: str, body: str) -> None:
        try:
            argv = ["notify-send", "--app-name=sprint-hub", title, body]
            subprocess.Popen(argv, env=session.env())
        except OSError:
            pass  # no notify-send: a missed popup must never stop the hub


class NullNotifier:
    def notify(self, title: str, body: str) -> None:
        pass
