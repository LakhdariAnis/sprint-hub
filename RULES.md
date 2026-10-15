# Rules

## Project format sprint-hub expects
- `<path>/.claude/commands/sprint-<id>.md` — one per step. Frontmatter: `description` (e.g. `Sprint 01a - Title`), `model`.
- `<path>/sprint/<id>-<slug>.md` — step spec; first lines shown in the side panel.
- `<path>/sprint/PROGRESS.md` — entries `## DATE — Step <id> ... (branch ...)`; an entry containing "Merged" counts as done.
- Git branches `step/<id>-<slug>`. Merged into main (and not identical to main) = done; exists but not merged = in progress; else todo.
- Projects listed in `~/.config/sprint-hub/projects.toml` (`[[project]]` with `name`, `path`).
- Start = `bw <id>` in a new terminal (`xdg-terminal-exec`) inside the project folder.

## Working on sprint-hub
- Never modify the projects it reads. Read only.
- Keep it working at every step. Small changes. Test before commit.
- Few files. Theme comes from `~/.local/state/omarchy/current/theme/colors.toml`.
