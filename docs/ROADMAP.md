# sprint-hub v2 — Roadmap

Status: 2026-10-16. This file sets the **scope and order** of v2. It overrides the `MVP` / `v2` / `later` tags in
`docs/HUB-DESIGN.md`. HUB-DESIGN stays the long-term picture. This file says what gets built, and when.

A version takes one or more sprints. Sprint sizes and weeks follow the time rules of the `new-sprint` skill (≤ 15 h planned of an 18 h budget, one ISO week each); the sprint table with weeks and ETA is in `sprint/README.md`. Each version ends with something that runs, tests that pass in CI and a short demo.
Only the current version has step files. Later sprints' steps are written when it starts, so the plan can use
what the last sprint taught.

---

## Rules for every version

These rules fix the four weak points from the review (2026-10-16).

### 1. The pitch is the engineering, not the AI
- The README leads with the system: *an event-driven daemon that runs a state machine over plain markdown files, with a
  human review gate before anything is merged*. Claude Code is one runner behind an adapter, not the headline.
- **Anis writes the README pitch, the state-machine section and every ADR "Decision / Why" himself.** The agent may
  write a list of questions or options, but never the answer. These are the parts an interviewer will ask about.

### 2. Every tool has to justify itself
- 0.2.0 uses only the tools in the table below. A new tool needs an ADR in `docs/decisions/` (template there)
  **before** the step that adds it: the problem it solves, the simpler choice it beats, and what it costs.
- Max two new tools per version.
- No tool is added "for the portfolio". If it would only look good, it stays out.

### 3. Code first, small commits
- No docs-only steps after `101`. Design happens inside the step that builds it (an ASCII sketch agreed in chat, then code).
- **Commit after every finished checklist task** (see `CLAUDE.md` → Commits). The git history must show the
  project growing in small working steps, not big dumps.
- Every step report ends with **"Explain-back"**: 3 questions about this step's code that Anis must be able to
  answer without notes. If he can't, the next step waits.

### 4. Never depend directly on things we don't control
**The problem, in plain words:** HUB-DESIGN reads Claude Code's private files (`~/.claude/projects/*.jsonl`,
`ai-title`, `cost-state`, …) and depends on Omarchy and Remote Control. Nobody promised those files will stay the
same. Anthropic can change them in any update without telling anyone. Then sprint-hub breaks one morning and nobody
can see why. A recruiter who tries the demo without Claude or Omarchy can't run it at all. That looks like a
project held together with tape.

**The fix:**
- **Adapters.** Everything outside our control sits behind one small interface in its own module:
  `AgentRunner` (Claude Code), `ThemeSource` (Omarchy), `Notifier` (notify-send), and later `UsageSource` (the
  Claude logs). The rest of the code talks only to the interface.
- **Documented things first.** Starting runs uses only documented CLI flags (`--model`, `--session-id`,
  `--resume`). Done detection uses a documented Claude Code **hook** (`Stop` / `SessionEnd`), not log parsing.
  Undocumented logs are used only for nice-to-have data (tokens, chat titles), never for the core loop.
- **A fake for each adapter.** `FakeRunner` simulates a Claude run (ticks a checklist, then reports done). Tests and
  `hubd --demo` use it, so anyone can run the full loop without Claude, Omarchy or my data.
- **Fail soft and say why.** If an undocumented file changes, the parser skips what it doesn't know and shows a
  warning. It never crashes. `hubd doctor` checks the installed `claude` version, its flags and the hook, and
  tells you what is wrong.
- **Contract tests.** Real samples (anonymised) of every outside format live in `tests/fixtures/`. When Claude Code
  updates, run the tests again with a fresh sample and you know at once whether something broke.

---

## Versions

### 0.2.0 — Core loop, laptop only (Sprints 1–2, ids `101`–`105`, `201`–`204`)
Start a step, watch the checklist live, the run ends, review it, approve (local merge) or request changes.
Runs fully in demo mode. Tests and CI are green.

Tools (the only ones allowed in 0.2.0):

| Tool | Why |
|---|---|
| Python 3.12 + uv | Same as v1, installs without sudo. |
| FastAPI + uvicorn | HTTP API + SSE with little code. |
| pydantic + python-frontmatter | Validate the md files and give clear errors. |
| watchfiles | React to file changes without polling. |
| Svelte + Vite + TypeScript | Live UI with little code. |
| git CLI, notify-send | Already on the machine. |
| pytest, Playwright, ruff, GitHub Actions | Tests, one e2e test, lint, CI. |

Cut from HUB-DESIGN's MVP: SQLite (an in-memory index rebuilt from the files is enough for one user), APScheduler,
markdown-it-py, Syncthing, Obsidian, ntfy, Tailscale, Remote Control. Each one can come back in a later version, with an ADR.

### 0.3.0 — Daily use (Sprints 3–4)
Things that make Anis use it every day instead of v1:
deadlines file + reminders (asyncio loop + notify-send), overdue on Today, manual tasks (`by: me`), questions inbox
(read-only), command palette, systemd user service, one-time read-only import of BenWhispers' state.

**Weekly planning** (new, from Anis 2026-10-16), same rules as the `new-sprint` skill:
- Read `hours:` from step frontmatter. Actual hours = agent time (run start → run-ended hook, recorded by hubd for every run) + Anis's own time not overlapping a run (entered on approve), written as `Time: <h> h (agent <a> h)` in PROGRESS.
- Sprint bar on the Project screen: planned / 15 h and actual / 18 h; turns red over budget.
- **Week view** on Today: this week's `work` sprint and `personal` sprint across all projects, hours done vs planned, days left in the week. Warns on two sprints in one track, or none in `work`.
- **Project ETA**: remaining sprints and hours, finish week, with the calibration factor (actual ÷ planned over the last 3 closed sprints).
- Close a sprint at week end: move unfinished steps to the next sprint, ask for actual hours.
- Data only from the md files (zero tokens). No calendar sync.


### 0.4.0 — Away from the laptop (Sprint 5)
Review and approve from the phone without building an app:
Syncthing + Obsidian approve flow, phone push (ntfy over Tailscale), `--remote-control` on runs.
Each of these new tools needs its ADR first. If one ADR can't justify its tool, cut that feature.

### 1.0.0 — Insight (Sprints 6–7)
`needs:` dependencies, create a step from the app, diff view, time and tokens per step, chat history, daily log.
Tokens and chats read the undocumented Claude logs through `UsageSource` (rule 4).

### Parked (not planned)
Phone app from IDC, Agent screen (skills, usage, setup), stats, weekly summary, `.ics` feed, skill health.
Unpark only with an ADR, and only after the internship applications are sent.
