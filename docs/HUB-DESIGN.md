# sprint-hub v2 — Design overview

Status: draft, 2026-10-16. Overview level only. Claude Code splits this into sprint steps.
**Scope and order: see `docs/ROADMAP.md`. It overrides the `MVP` / `v2` / `later` tags below.**
The current sprint-hub (`~/Work/sprint-hub`) and BenWhispers stay untouched. v2 is built on its own branch.

---

## 1. Vision

sprint-hub v2 is the control room for work that Claude Code and I do together. Every piece of work runs through
one loop: **spec → done (by Claude or by me) → reviewed → approved**. A vault of markdown files is the source of
truth, and a small daemon watches it and acts on it. The app is a keyboard-first window on the laptop, with Obsidian
and the phone for review and approval from anywhere.
It is not a generic todo app. It holds only work that fits the loop, plus deadlines that must not be missed.

### Daily routine it supports
My days have no fixed shape (school, remote dev job, side projects). So the Hub does not plan time blocks. It
answers four questions whenever I open it:
1. **What is running?** Steps Claude is working on now, with live checklists.
2. **What waits for me?** The review queue (Claude finished) and open questions from Claude.
3. **What is due?** Deadlines in the next 7 days (school, internship, client).
4. **What can I start next?** Todo steps whose dependencies are approved.

Typical moments:
- Start of a work block: open Today, start one or two steps (or one task of a step) with the right model.
- Away from the laptop: get a push on the phone ("Step 05a done"), read the summary, approve or request changes.
- End of the day: clear the review queue. The daily log writes itself.

---

## 2. Users and use cases

One user: me. Built so a recruiter can run the demo, but there are no multi-user features.

| Area | Use cases |
|---|---|
| **Work** (remote dev, e.g. BenWhispers) | Run sprint steps with Claude, review the diff, approve (local merge) or request changes, reopen the Claude chat to ask why. |
| **Side projects** (autonomous_car, tinyml-bearing-fault, …) | Same loop as work. Several projects at once on one Today screen. |
| **School (ESI)** | Deadlines (assignments, exams, PFE), and manual tasks inside a school project. |
| **Internship hunt** | Deadlines and follow-ups (MVP). v2: an internship project whose steps Claude drafts with my existing skills (`outreach-email`, `cv-writing`) and I review like code. |

Out of scope: habits, streaks, generic personal todos, time blocking, calendar sync.

---

## 3. Features

### Core loop
- **Multi-project index** `MVP`: all projects from the vault on one screen. Each project points to a repo path, or has none (non-code).
- **Strict md format** `MVP`: projects, steps and tasks use frontmatter plus fixed sections. The daemon validates them and shows clear errors for broken files.
- **States** `MVP`: todo, doing, done, approved, and changes requested (section 4). Shown everywhere with the same colours and icons.
- **Start a step** `MVP`: opens a new terminal with `claude` in the repo, using the step's model (opus / sonnet / haiku), on branch `step/<id>-<slug>`.
- **Remote Control** `MVP`: every run starts with `--remote-control <step-id>`, so the live session also shows up in the Claude mobile app. There I can approve permission prompts and chat with the run. On by default, turned off with `remote_control: false` per project or per step.
- **Start one task** `MVP`: start a single checklist item of a step. Claude is told to do only that task.
- **Live checklist** `MVP`: the tasks Claude ticks while working, updated live in the UI.
- **Session link and resume** `MVP`: every run is recorded with its Claude session id. One key reopens that chat (`claude --resume <id>`).
- **Done detection** `MVP`: a Claude Code hook tells the daemon when a run ends. The step moves to done and a notification fires.
- **Approve** `MVP`: marks the step approved and merges the step branch into main locally. Never pushes. On conflict it stops and notifies.
- **Request changes** `MVP`: my comment is saved in the step's review file. The step goes back, and the next run resumes the same chat with the comment.
- **Manual tasks** `MVP`: steps or tasks with `by: me`. Same states, but I tick them myself. Used for school, internship and work chores.
- **Create a step from the app** `v2`: a short form (title, model, tasks, deps) writes the files in the same format as the `new-sprint-step` skill.
- **Dependencies** `v2`: `needs:` in frontmatter. Blocked steps are greyed out and cannot be started.
- **Auto-queue** `later`: after I approve a step, offer to start the next unblocked step.

### Today and review
- **Today screen** `MVP`: running, waiting for review, questions, deadlines, next up, across all projects.
- **Review queue** `MVP`: done steps, oldest first. Shows Claude's final report, the files changed (diffstat) and the checklist.
- **Questions inbox** `MVP` read-only, `v2` answer: questions Claude wrote during a run. In v2 I answer in the app and the chat resumes with my answer.
- **Diff view** `v2`: the step branch diff against main inside the app.

### Deadlines and reminders
- **Deadlines file** `MVP`: one line per deadline in `~/Hub/deadlines.md`, plus an optional `due:` on any step or task. Easy to add from Obsidian on the phone.
- **Reminders** `MVP`: desktop notification (mako) and a phone push (ntfy over Tailscale), 3 days before, 1 day before, and on the day.
- **Overdue view** `MVP`: overdue items stay at the top of Today until done or moved.
- **Calendar feed (.ics)** `later`: only if I miss seeing deadlines in a calendar.

### Tracking and logs
- **Time and tokens per step** `v2`: wall time and token count read from the Claude session logs. No dollar cost (Pro/Max subscription).
- **Daily log** `v2`: the daemon writes `~/Hub/log/YYYY-MM-DD.md` (what started, finished, got approved, tokens, time). Readable in Obsidian.
- **Weekly summary** `later`: one page per week, generated from the daily logs.
- **Stats** `later`: per project, steps per week, review turnaround, changes-requested rate, model mix.

### Chats
- **Chat history per project** `v2`: every Claude Code chat run in the project's repo (read from `~/.claude/projects/<repo-path>/`), newest first: title, date, length, model, linked step, lines changed. `Enter` resumes it (`claude --resume <id>`). Preview shows the first prompt and the last answer.
- **Automatic titles** `v2`: use the `ai-title` Claude Code already writes for each chat (no extra tokens, no skill needed). Fallback: the first prompt. I can rename a chat in the Hub; the name is saved in the vault, never in Claude's files.
- **Link chats to steps** `v2`: chats started by the Hub are linked by session id. Other chats can be linked to a step by hand.
- **Chat chains** `v2`: follow `continued-in` so a chat that was continued shows as one thread.
- **Search chats** `later`: full-text search over all chat logs.

### Agent (my Claude Code setup)
- **Skills view** `v2`: every skill in `~/.claude/skills/` and from plugins, with its description, use count and last use (read from session logs). One key opens the `SKILL.md` in `$EDITOR`. Plugin skills are read-only.
- **Usage view** `v2`: tokens and time per day, per project, per model, and per skill. Built on the same session-log parsing as "Time and tokens per step".
- **Project setup view** `v2`: per project, which `CLAUDE.md`, slash commands (`.claude/commands/`) and hooks apply. Shows broken or missing pieces (no checklist rule, no step command).
- **Skills per step** `later`: `skills:` in step frontmatter. The run prompt tells Claude to use them, and the review shows which skills were used.
- **Skill health** `later`: skills never used in 30 days, skills whose description never triggers, and a "turn this into a skill" hint when the same request repeats across sessions.

### Phone
- **Approve from Obsidian** `MVP`: I edit one field in the step's review file on the phone. Syncthing syncs it and the daemon acts.
- **Approve permission prompts** `MVP`: through Claude Code Remote Control in the Claude mobile app (see Core loop). Nothing to build, and it does not go through the Hub.
- **Push notifications** `MVP`: ntfy for "done", "question", "merge conflict" and deadline reminders.
- **Phone app** `v2`: a native Android app built from my IDC app (`~/Projects/IDC`). Today, review queue (report, diffstat, checklist), approve, request changes, answer questions, add and tick deadlines, live checklist of running steps. Native notifications over its own connection replace ntfy. It never starts runs (laptop only).
- **Clipboard sync** `v2`: kept from IDC as a bonus (phone to laptop clipboard).
- **Pairing** `v2`: QR code shown on the laptop gives the phone a secret token. No automatic pairing.

### Look and feel
- **Omarchy theme** `MVP`: all colours come from `~/.local/state/omarchy/current/theme/colors.toml`. The app restyles live when I switch theme.
- **Keyboard-first** `MVP`: every action has a key. A command palette finds any project, step or action.
- **Own window** `MVP`: opens as an app window (no browser tabs) from a Hyprland binding.

---

## 4. Data model

### Entities
| Entity | What it is | Lives in |
|---|---|---|
| **Project** | A repo or a non-code area (school, internship). Name, repo path (optional), default model, merge rule. | `~/Hub/projects/<project>/project.md` |
| **Step** | One unit of work with a spec, a state and tasks. `by: claude` or `by: me`. | Spec: in the repo (`sprint/<id>-<slug>.md`). State and review: in the vault (`~/Hub/projects/<project>/steps/<id>.md`). Non-code projects: vault only. |
| **Task** | One checklist item inside a step. Can be started alone. | `## Tasks` section of the spec. Live ticks in `sprint/progress/<id>.md`, which Claude writes. |
| **Run** | One Claude Code session on a step or task: session id, model, start, end, tokens, result. | Listed in the vault step file. |
| **Review** | My verdict on a run: approve or request changes, with a comment. | `## Review` section of the vault step file. |
| **Question** | Something Claude asks me during a run, and my answer. | `## Questions` section of the vault step file. |
| **Chat** | Any Claude Code session in a project's repo: id, title (`ai-title` or my rename), dates, model, cost-state, linked step. A Run is a Chat the Hub started. | Read from `~/.claude/projects/<repo-path>/<id>.jsonl`. My renames and links live in `~/Hub/projects/<project>/chats.md`. |
| **Skill** | A Claude Code skill: name, description, source (mine or a plugin), use count, last use. | `~/.claude/skills/<name>/SKILL.md` (read-only to hubd). |
| **Deadline** | Date, text, tags, an optional link to a project or step. | `~/Hub/deadlines.md`, or `due:` in frontmatter. |
| **Log entry** | What happened on one day. | `~/Hub/log/YYYY-MM-DD.md` (written by the daemon). |

### Step states
```
todo ──start──▶ doing ──run ends──▶ done ──approve──▶ approved (merged)
                  ▲                   │
                  └── changes ◀───────┘ request changes (comment)
```
- `blocked` is not stored. It is computed when a `needs:` step is not approved.
- Task states: `[ ]` todo, `[~]` doing, `[x]` done (same as the current checklist format).
- Only the daemon moves a step to `doing` and `done`. Only I move it to `approved` or `changes`.

### Vault layout
```
~/Hub/
  hub.toml                      # settings: projects root, reminder times, ntfy topic
  deadlines.md
  projects/<project>/project.md
  projects/<project>/steps/<id>.md   # state, runs, review, questions
  log/YYYY-MM-DD.md
```

### File format (short example)
`~/Hub/projects/benwhispers/steps/05a.md`:
```markdown
---
step: 05a
title: Home — boutique focus list
state: done            # todo | doing | done | changes | approved
by: claude
model: sonnet
branch: step/05a-home-focus-list
needs: [04]
due: 2026-10-24
---

## Runs
- 2026-10-15 21:40 · sonnet · session 3f2a…c91 · 42 min · 1.2M tokens · task all

## Review
verdict:               # I write: approve | changes
comment:

## Questions
- Q: Use first-frame posters or design-3 posters? — A:
```

`~/Hub/deadlines.md`:
```markdown
- 2026-11-03 Fraunhofer IPA application #internship
- 2026-11-10 Compilation TP report #school
```

The spec files in the repo keep the current format (`sprint/<id>-<slug>.md`, `.claude/commands/sprint-<id>.md`,
`sprint/progress/<id>.md`), so BenWhispers works without changes.

---

## 5. Architecture

```
 Obsidian (laptop + phone) ──edits──▶ ~/Hub vault ◀── Syncthing ──▶ phone
                                          │ watch
 Svelte UI (app window) ◀─HTTP + SSE─▶ hubd daemon ──git / spawn terminal──▶ repos + claude
 Phone app (v2, IDC) ◀─ WS, Tailscale ─▶   │  ▲
                                            │  └── Claude Code hook (run ended) ── POST localhost
                                            ├──▶ mako (notify-send)
                                            └──▶ ntfy ──▶ phone push
```

- **Vault** (`~/Hub`): the source of truth for state, reviews, questions, deadlines and logs. Plain md, readable without the app.
- **`~/.claude`**: skills, session logs and settings. hubd reads them for runs, usage and the Agent screen. It writes only one thing there: the run-ended hook.
- **Repos**: hold step specs and code. The Hub reads them. It writes to them only through git (branch, merge) and by creating new step files on request.
- **hubd (daemon)**: one Python process, run as a systemd user service.
  - Watches the vault and repos. Parses and validates files. Keeps a SQLite index as a fast cache (it can always be rebuilt from the md files).
  - Runs a small, fixed set of actions: start a run, merge, send a notification, write a log. Nothing else.
  - Serves the HTTP API, an SSE stream for live updates, and the built Svelte UI.
  - Schedules deadline reminders.
- **UI**: Svelte single-page app served by hubd, opened as an app window (`omarchy-launch-webapp`). Talks only to hubd.
- **Claude Code**:
  - Started by hubd in a new terminal (`xdg-terminal-exec`), with a session id chosen up front (`--session-id`), so the run is linked before it starts.
  - Started with `--remote-control <step-id>` (unless turned off), so the session can be followed and its permission prompts approved from the Claude mobile app. This goes through my Claude account, not through hubd.
  - A user-level hook (`~/.claude/settings.json`, so client repos stay clean) fires when the session ends and tells hubd on localhost. The hook only acts when the env variable from hubd is set.
  - Writes the live checklist and its questions as it does today.
- **Phone**:
  - MVP: Obsidian + Syncthing to edit the vault (approve, deadlines), ntfy for pushes, and the Claude mobile app for Remote Control of running sessions.
  - v2: the phone app, reworked from IDC. Its Flutter client (foreground service, persistent WebSocket, pairing, inbox, design) is reused. The IDC Python daemon is not run: its typed `{type, payload}` message router moves into hubd as a WebSocket endpoint, so there is one daemon with one set of allowed commands. The app connects over Tailscale (LAN discovery only as a fallback at home). ntfy is then dropped.

Token rules:
- hubd never calls a model by itself. Parsing, titles, usage, reminders and merges cost zero tokens.
- Prefer one session per step. Starting single tasks makes each new session read the spec and files again.
- Request changes resumes the same chat only while it is small. A long chat (e.g. over ~150k tokens of context) gets a fresh session with a short summary of the review comment and the diff instead.

Flow example (approve from phone): I set `verdict: approve` in Obsidian on the phone → Syncthing syncs →
hubd sees the change and validates it → merges the branch locally → sets `state: approved` → logs it → pushes
"05a merged" to the phone.

---

## 6. Tools and stack

| Tool | Why |
|---|---|
| **Python 3.12 + uv** | Same as sprint-hub. uv gives reproducible installs without sudo. |
| **FastAPI + uvicorn** | Small, typed HTTP API with SSE support. Auto-generated API docs help the portfolio. |
| **watchfiles** | Fast file watching (Rust-based) for the vault and the progress files. |
| **pydantic** | One schema per file type. Validates frontmatter and gives clear errors. |
| **python-frontmatter + markdown-it-py** | Read frontmatter and the fixed sections of md files. |
| **SQLite (stdlib)** | Rebuildable index for fast Today and search queries. Not the source of truth. |
| **git CLI (subprocess)** | Branch state and local merges. No extra library, same behaviour as my terminal. |
| **APScheduler** (or a small asyncio loop) | Deadline reminders at fixed times. |
| **SvelteKit (static adapter) + TypeScript + Vite** | Reactive UI for live checklists, keyboard navigation and a command palette. Built to static files that hubd serves. |
| **SSE** | One-way live updates from hubd to the UI. Simpler than WebSockets. |
| **Claude Code CLI + hooks** | Start runs (`--model`, `--session-id`, `--remote-control`), resume chats (`--resume`), detect the end of a run. |
| **Claude mobile app (Remote Control)** | Approve permission prompts and talk to a running session from the phone. No hosting. |
| **Omarchy theme file** | `colors.toml` mapped to CSS variables. The UI matches the desktop. |
| **mako / notify-send** | Desktop notifications, already part of Omarchy. |
| **ntfy (self-hosted, Tailscale only)** | MVP phone push without a public service. Dropped in v2 when the phone app arrives. |
| **Flutter + flutter_foreground_task + web_socket_channel** (v2) | The phone app, reused from IDC. A foreground service keeps the link to hubd open for live updates and notifications. |
| **Syncthing** | Device-to-device sync of the vault. No cloud. |
| **Obsidian** | Read and edit the vault on laptop and phone. |
| **Tailscale** | Private network for ntfy and, in v2, the phone app. |
| **systemd user service** | Starts hubd at login and restarts it on a crash. |
| **pytest + Playwright** | Unit tests for parsing and state rules. One end-to-end test of the main loop. |
| **GitHub Actions** | CI for tests, lint and the UI build. Shows code quality on the public repo. |

---

## 7. Main screens and keys

### Screens
1. **Today**: running, review queue, questions, deadlines (7 days plus overdue), next up.
2. **Projects**: all projects with step counts per state.
3. **Project**: steps in order, with state, model, deps and checklist progress.
4. **Step**: spec, live checklist, runs (with sessions), review, questions.
5. **Review queue**: done steps with report, diffstat and checklist. Approve or request changes.
6. **Questions**: open questions across projects.
7. **Deadlines**: list by date. Add, move, mark done.
8. **Chats** (v2): chat history per project, also a tab on the Project screen.
9. **Log** (v2): daily log pages.
10. **Agent** (v2): skills, usage, and project setup.
11. **Command palette**: overlay on every screen.

### Keys
| Key | Action |
|---|---|
| `Super+Shift+S` | Open or focus the app (Hyprland binding, as today) |
| `Ctrl+K` or `:` | Command palette |
| `g t` / `g p` / `g r` / `g q` / `g d` / `g c` / `g a` | Go to Today / Projects / Review / Questions / Deadlines / Chats / Agent |
| `j` / `k`, `Enter`, `Esc` | Move, open, back |
| `s` | Start the selected step (model from frontmatter) |
| `t` | Start only the selected task |
| `m` | Change model before starting |
| `o` | Open the linked Claude chat (`claude --resume`) |
| `a` | Approve (confirm, then merge) |
| `c` | Request changes (comment box) |
| `x` | Tick a manual task or deadline |
| `n` | New step (v2) or new deadline |
| `e` | Open the file in `$EDITOR` |
| `/` | Filter the current list |
| `?` | Key help |

---

## 8. Security and privacy rules

- **Sync only between my own devices.** Syncthing with known device ids only. No cloud sync and no shared folders.
- **The daemon accepts only known commands.** A vault edit can only trigger a fixed set of transitions: approve, request changes, answer a question, tick a manual task, add a deadline. It never runs a command or a prompt written in a file.
- **No automatic pairing.** IDC today accepts any new device. The Hub version pairs only through a QR code shown on the laptop, and a paired device can be revoked from the laptop.
- **The phone app accepts only the fixed message types**: approve, request changes, answer, tick, add deadline, clipboard. Anything else is dropped and logged.
- **The phone cannot start Claude runs** (MVP and v2). Start is laptop-only. A comment from request changes is passed to Claude as text in a resumed chat, and only for a step that is already in review.
- **Network**: hubd listens on `127.0.0.1` only. In v2 it also listens on the Tailscale interface, for the phone app only, with TLS (`wss://`) or Tailscale's encryption, and a per-device token checked on every connection. Never on `0.0.0.0`. ntfy is reachable only over Tailscale. Notification text is short (project, step id, title) and contains no code or client data.
- **Remote Control is the only way the phone approves tool calls.** It goes through my logged-in Claude account, not through vault files, so file edits still never trigger the agent. Anyone with my unlocked phone could approve commands on the laptop, so the phone stays locked. Remote Control can be turned off per project.
- **Claude permissions are never loosened.** hubd never passes `--dangerously-skip-permissions`. Runs use my normal Claude Code permission settings.
- **Git safety**: merge only into main, only on approve, never push, never force, never delete branches. Stop on conflict and notify. A per-project `merge: manual` turns the merge off.
- **Client repos stay clean.** No hub files in client repos except the sprint files that already exist. The hook is user-level, not per repo.
- **`~/.claude` is read-only to hubd**, except for installing its own hook. Skills and settings are edited only by me, in my editor.
- **Validate before acting.** A broken or unknown file is shown as an error and ignored. Every automatic action is written to the daily log.
- **Demo data is fake.** The public repo and the demo use a sample vault, with no client code, names or BenWhispers content.

---

## 9. Portfolio angle

- **Story**: "A control room for AI coding agents. Markdown files are the API, a daemon steers Claude Code runs, and I review and approve from anywhere." It shows systems thinking (daemon, events, state machine, sync), product design, and AI tooling.
- **What to show**:
  - The state machine and the "markdown is the API" architecture diagram in the README.
  - The live checklist ticking while Claude works.
  - Theme switching: the app restyles live with Omarchy themes.
  - Clean code: typed API, schema validation, tests, CI.
  - v2: one protocol across three clients (laptop UI, phone app, Obsidian files), with secure QR pairing.
- **Demo idea (60–90 s video)**: start a step on the laptop → checklist ticks live → phone gets a push "done" →
  approve on the phone in Obsidian → laptop merges and the Today screen updates → press `o` to reopen the chat and ask why.
- **Demo mode**: `hubd --demo` loads a sample vault and a fake repo, so anyone can try it without Claude or my data.
- **README**: short pitch, GIF, architecture diagram, data model, security rules, and how to run the demo.

---

## 10. Open questions left

1. **Reminders when the laptop is off**: ntfy (MVP) and the phone app (v2) both need the laptop awake, so no pushes when it sleeps. In v2 the app could keep a local copy of deadlines and remind on its own. Options: accept it, use a phone-side reminder app, or add the `.ics` feed later.
2. **Done detection**: which Claude Code hook event fits best (session end vs. stop), and how to tell "finished" from "I closed the terminal"? Settle in the first build step.
3. **Questions channel**: Claude writes questions to the progress file or to the vault step file? (BenWhispers today uses `sprint/QUESTIONS.md`.)
4. **Task-level start**: the prompt that keeps Claude to one task, and what happens to the step state when only some tasks are done.
5. **Merge style**: `--no-ff` merge commit or fast-forward, and per-project defaults (client repos may want `merge: manual`).
6. **Migration**: import BenWhispers' current state (branches, `PROGRESS.md`) into the vault once, read-only on the repo.
7. **Spec location for new projects**: keep specs in the repo (hybrid, as decided), or allow vault-only specs for small projects?
8. **Internship project (v2)**: link it to `internship/tracker.csv`, or replace the CSV with vault steps?
9. **IDC rework scope**: which IDC screens stay (remote mouse, keyboard, sensors, easter eggs) and which are cut to keep the app focused.
10. **Plan limits**: can the Usage view show how much of the Pro/Max limit is left? Only if Claude Code exposes it in a file or command. Otherwise show tokens only.
11. **Claude log format**: `~/.claude/projects/*.jsonl` (`ai-title`, `cost-state`, `continued-in`) is internal and undocumented, so it can change with any Claude Code update. The parser must skip unknown lines and never crash.
