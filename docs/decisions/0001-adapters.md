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

## Decision
TODO(Anis)

## Why
TODO(Anis)
