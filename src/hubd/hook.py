"""Claude Code hook: tells hubd that a hub-started run ended or waits for Anis.

One script for `SessionEnd` (run ended), `Stop` (turn done) and `Notification` (permission or
idle prompt). Claude runs it for every session on the machine, so it must be fast, import little,
do nothing outside hub runs, and never fail. Docs: https://code.claude.com/docs/en/hooks
"""

import json
import os
import sys
import urllib.request
from collections.abc import Mapping
from typing import TextIO

# SessionEnd hooks get 1.5 s in total by default; Stop holds Claude while it runs.
TIMEOUT = 1.0
# `notification_type` -> kind; other types (auth, elicitation, ...) send nothing.
NOTIFICATIONS = {"permission_prompt": "permission", "idle_prompt": "idle"}


def request(event: dict, step: str) -> tuple[str, dict] | None:
    """The hubd path and body for this hook event, None when hubd needs no word."""
    name = event.get("hook_event_name", "SessionEnd")
    body = {"session_id": event["session_id"], "step": step}
    if name == "SessionEnd":
        return "/runs/ended", body
    if name == "Stop" and not event.get("stop_hook_active"):  # a hook made Claude go on
        return "/runs/waiting", {**body, "kind": "turn"}
    if name == "Notification" and (kind := NOTIFICATIONS.get(event.get("notification_type"))):
        return "/runs/waiting", {**body, "kind": kind}
    return None


def main(stdin: TextIO = sys.stdin, env: Mapping[str, str] = os.environ) -> int:
    step = env.get("HUB_RUN")
    if not step:
        return 0  # not a hub run
    try:
        sent = request(json.load(stdin), step)
        if sent is None:
            return 0
        path, body = sent
        req = urllib.request.Request(
            env.get("HUB_URL", "http://127.0.0.1:8765") + path,
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=TIMEOUT).close()
    except (OSError, ValueError, KeyError, AttributeError, TypeError):
        pass  # hubd down or odd input: never block or break Claude
    return 0


if __name__ == "__main__":
    sys.exit(main())
