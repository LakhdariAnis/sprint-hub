#!/usr/bin/env bash
# Records one real `claude -p` session as tests/fixtures/claude-stream-json/claude-<version>.jsonl.
# Run from anywhere: tests/fixtures/claude-stream-json/make-sample.sh
set -euo pipefail
out=$(cd "$(dirname "$0")" && pwd)
version=$(claude --version | cut -d' ' -f1)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
touch "$work/notes.txt"
cd "$work"
echo '{"type":"user","message":{"role":"user","content":"Run ls, then say hi in one word."},"parent_tool_use_id":null}' |
  claude -p --input-format stream-json --output-format stream-json --verbose \
    --include-partial-messages --permission-mode default --permission-prompts none \
    --model haiku --session-id "$(python3 -c 'import uuid; print(uuid.uuid4())')" |
  python3 -I -c '
import json, re, sys
for line in sys.stdin:
    m = json.loads(line)
    if m.get("subtype", "").startswith("hook_"):
        continue  # hook output is the machine owner'"'"'s
    if m.get("subtype") == "init":  # skill, plugin and MCP names are the owner'"'"'s too
        m = {k: m[k] for k in ("type", "subtype", "cwd", "session_id", "model")}
    text = json.dumps(m, ensure_ascii=False)
    text = re.sub(r"\"signature\": ?\"[^\"]*\"", "\"signature\":\"\"", text)
    text = re.sub(r"/home/[^\" ]*", "/PATH", text)
    text = re.sub(r"/tmp/tmp\.\w+", "/tmp/sample", text)
    text = re.sub(r"-tmp-tmp-\w+", "-tmp-sample", text)
    print(text)
' > "$out/claude-$version.jsonl"
echo "wrote $out/claude-$version.jsonl"
