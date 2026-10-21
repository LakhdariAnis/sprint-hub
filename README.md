# sprint-hub

<!-- TODO(Anis): write the pitch in your own words (2–4 sentences). Guiding questions:
1. What problem did you have that made you build this? Name one concrete moment.
2. ROADMAP rule 1 says lead with the system: an event-driven daemon, a state machine over plain markdown files,
   and a human review gate before anything is merged. Do you agree with that order, or does something else come first?
3. What should a reader know after the first sentence, before they try the demo?
-->

## Try it

Needs `uv` and Node 24. No Claude, Omarchy or your own projects needed: the demo runs on built-in data with a fake runner.

    cd web && npm ci && npm run build && cd ..   # once: builds the UI that hubd serves
    uv run hubd --demo

Open http://127.0.0.1:8765/. Keys: `1 2 3` switch screens, arrows walk the list, `Enter` opens, `s` starts a step
(Step screen), `a` approves and `c` requests changes (Review), `?` shows all keys.

## Screenshots

<!-- TODO(Anis): retake these from the 0.2.0 build before the release, or drop them. -->

![Today](sprint/screens/213c-today.png)
![Step spec](sprint/screens/213d-step-spec.png)

## How it works

<!-- TODO(Anis): write the state-machine section in your own words. Start from docs/states.md (the diagram).
Guiding questions:
1. Why may only the daemon move a step to `doing` and `done`, and only you to `approved` and `changes`?
   What would go wrong if Claude could mark its own step `approved`?
2. Where does the source of truth live (the markdown files), and what happens to the state when hubd restarts?
3. What is the review gate for, in one sentence?
-->

## Tests and CI

    uv run pytest                  # API, model, runner and hook tests; no Claude needed
    uv run ruff check              # lint
    cd web && npm run build && npm run e2e   # one browser test of the demo loop (Playwright)

The e2e test (`web/e2e/loop.spec.ts`) starts `hubd --demo` itself. `tests/fixtures/` holds anonymised samples of the
outside formats (the vault files, the Claude Code hook input), so a change in those formats shows up as a failing test.
CI (`.github/workflows/ci.yml`) runs all of the above on every push and pull request.

## Roadmap

Versions and scope: [docs/ROADMAP.md](docs/ROADMAP.md). Long-term design: [docs/HUB-DESIGN.md](docs/HUB-DESIGN.md).
Current version: 0.2.0 (core loop, laptop only). The v1 Textual app is on `main` (tag `v0.1.0`).
