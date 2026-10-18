#!/usr/bin/env bash
# Run step demo/102 with FakeRunner against a throwaway copy of the fixture vault.
set -euo pipefail
cd "$(dirname "$0")/.."
S=$(mktemp -d /tmp/hubtry.XXXX)
trap 'kill $(jobs -p) 2>/dev/null; rm -rf "$S"' EXIT
cp -r tests/fixtures/vault "$S/vault"
rm -f "$S/vault/demo-repo/sprint/progress/102.md"
sed -i 's/^state: doing.*/state: todo/; s/^needs:.*/needs: []/; /^- 2026/d' "$S/vault/projects/demo/steps/102.md"

uv run python - "$S/vault" >"$S/daemon.log" 2>&1 <<'PY' &
import sys
from pathlib import Path
import uvicorn
from hubd.api import create_app
from hubd.daemon import Hub
from hubd.notify import NullNotifier
from hubd.runners.fake import FakeRunner

hub = Hub(Path(sys.argv[1]), lambda ended: FakeRunner(ended, delay=1), NullNotifier())
uvicorn.run(create_app(hub), host="127.0.0.1", port=8765)
PY

until curl -sf localhost:8765/health >/dev/null; do sleep 0.2; done
curl -sN localhost:8765/events | grep --line-buffered '^event:' | sed 's/^/SSE  /' &
sleep 0.5
echo "== start"; curl -s -XPOST localhost:8765/steps/demo/102/start | head -c 200; echo
until [ "$(curl -s localhost:8765/steps/demo/102 | python3 -c 'import json,sys;print(json.load(sys.stdin)["state"])')" = done ]; do sleep 0.5; done
sleep 0.5
echo "== progress file"; cat "$S/vault/demo-repo/sprint/progress/102.md"
echo "== step file"; head -5 "$S/vault/projects/demo/steps/102.md"; grep -A2 '^## Runs' "$S/vault/projects/demo/steps/102.md"
