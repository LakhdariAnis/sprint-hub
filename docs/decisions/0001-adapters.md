# ADR 0001 — Adapters and fakes for outside tools

Date: 2026-10-16 · Status: proposed

## Problem
sprint-hub depends on things we do not control: Claude Code (flags, hooks, logs), Omarchy (theme), notify-send.
Any of them can change in an update. Without a boundary, a change breaks the core loop in many places, and nobody
can run the demo or the tests without Claude or Omarchy installed.

## Options
1. **Direct calls.** Call `claude`, read Omarchy files and run `notify-send` where needed.
   Least code now. Tests need the real tools or patching of `subprocess`. A change in a tool touches every caller.
2. **Adapters + fakes** (ROADMAP rule 4). One small interface per outside tool (`AgentRunner`, `ThemeSource`,
   `Notifier`), one real class and one fake (`FakeRunner`). The rest of the code uses only the interface.
   More files and one extra class per tool. Tests and `hubd --demo` run without the real tools. A tool change touches one module.
3. **Adapters only for the Claude runner.** Interface and fake for `AgentRunner`, direct calls for theme and notifications.
   Covers the biggest risk with less code. Theme and notify changes still spread.

### What steps 108–111 showed (facts for the options, not a decision)
- **Fake.** `FakeRunner` (`runners/fake.py`, ~50 lines) runs the whole tick-then-end loop in tests with no Claude,
  in under a second. To see each tick, the test swaps the runner's `sleep`; nothing else is patched.
- **The interface moved once.** Writing the real runner (109) showed `resume` also needs the step: the hook needs
  `HUB_RUN=<step id>`, and a session→step map in memory is lost when hubd restarts. With options 2 and 3 that was a
  change to `base.py`, `fake.py` and one test. With option 1 it would have touched each caller.
- **Flags in one place.** `runners/claude.py` names `--model`, `--session-id`, `--resume` once, with the doc link.
  `hubd doctor` reads the same names, so a renamed flag is one edit and shows as ✘ before a run fails.
- **More outside formats than planned.** The done signal adds two contracts: the `SessionEnd` hook input on stdin
  and the `hooks` block in `~/.claude/settings.json`. A real hook input is in `tests/fixtures/hook/` (captured with
  `claude --init-only`, no tokens spent).
- **Cost.** `runners/` is 3 files, ~120 lines with the protocol; one direct `subprocess.Popen` call would be ~15.
  The notifier (`Notifier`, step 112) and the theme source are not built yet, so options 2 and 3 differ only in code not written yet.

## Decision
TODO(Anis)

## Why
TODO(Anis)
