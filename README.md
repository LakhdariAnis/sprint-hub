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
