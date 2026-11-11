# Claude Code stream-json samples

`claude-<version>.jsonl` is the stdout of one real `claude -p` session (`--output-format
stream-json`): a `ls` tool call, its result, a short answer. `tests/test_chat_fixture.py` feeds
every sample to the chat parser (`src/hubd/runners/chat.py`) and checks the events it makes.

## After a Claude Code update

    tests/fixtures/claude-stream-json/make-sample.sh

It runs `claude` (haiku, a few cents at most) in a temp folder and writes
`claude-<new version>.jsonl` here. Then `uv run pytest -k fixture`.

- Test fails: Claude Code changed its output. Fix the parser, keep the old sample so older
  versions stay covered, commit both.
- Test passes: commit the new sample. Delete older ones only if you want less to read.

The script drops hook output and the `init` details (skills, plugins, MCP names), blanks the
thinking signature, and rewrites paths under `/home` and the temp folder. Read the new file before
committing it: no private text may be in it.
