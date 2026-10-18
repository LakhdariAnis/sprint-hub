"""Claude Code `SessionEnd` hook: tells hubd that a hub-started run ended.

Claude runs this for every session on the machine, so it must be fast, import little,
do nothing outside hub runs, and never fail. Docs: https://code.claude.com/docs/en/hooks#sessionend
"""

import json
import os
import sys
import urllib.request
from collections.abc import Mapping
from typing import TextIO

# SessionEnd hooks get 1.5 s in total by default.
TIMEOUT = 1.0


def main(stdin: TextIO = sys.stdin, env: Mapping[str, str] = os.environ) -> int:
    step = env.get("HUB_RUN")
    if not step:
        return 0  # not a hub run
    try:
        event = json.load(stdin)
        body = json.dumps({"session_id": event["session_id"], "step": step}).encode()
        request = urllib.request.Request(
            env.get("HUB_URL", "http://127.0.0.1:8765") + "/runs/ended",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(request, timeout=TIMEOUT).close()
    except (OSError, ValueError, KeyError):
        pass  # hubd down or odd input: never block or break Claude
    return 0


if __name__ == "__main__":
    sys.exit(main())
