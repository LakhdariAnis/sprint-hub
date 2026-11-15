"""Desktop notifications behind one interface (docs/ROADMAP.md rule 4)."""

import subprocess
import threading
from collections.abc import Callable
from typing import Protocol

from hubd import session

Click = Callable[[], None]


class Notifier(Protocol):
    def notify(self, title: str, body: str, on_click: Click | None = None) -> None:
        """`on_click`: called when Anis clicks the popup, if the notification daemon can."""
        ...


class NotifySend:
    def notify(self, title: str, body: str, on_click: Click | None = None) -> None:
        argv = ["notify-send", "--app-name=sprint-hub", title, body]
        if on_click is None:
            try:
                subprocess.Popen(argv, env=session.env())
            except OSError:
                pass  # no notify-send: a missed popup must never stop the hub
            return
        # `--action` waits until the popup closes: in a thread, so hubd never blocks on it.
        threading.Thread(
            target=_wait, args=([*argv, "--action=default=Open"], on_click), daemon=True
        ).start()


def _wait(argv: list[str], on_click: Click) -> None:
    try:
        picked = subprocess.run(argv, env=session.env(), capture_output=True, text=True).stdout
    except OSError:
        return
    if picked.strip() == "default":  # no action support: the popup shows, nothing is printed
        on_click()


class NullNotifier:
    def notify(self, title: str, body: str, on_click: Click | None = None) -> None:
        pass
