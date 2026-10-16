# sprint-hub v2

Branch `v2` is the rebuild described in `docs/HUB-DESIGN.md`. Scope and order come from `docs/ROADMAP.md` (it overrides the HUB-DESIGN scope tags); follow its rules. Branch `main` is the current sprint-hub: never change it from here.

## Checklist

When working on a sprint step, after the plan write `sprint/progress/NN.md` (NN = step id, e.g. `02`, `01a`) before the first edit. First line `# Step NN`, then one line `- [ ] <task>` per task in the step file. Mark the task you are on `- [~]` (only one at a time) and change it to `- [x]` as soon as it is done. Edit the file right away, not in a batch at the end: sprint-hub shows it live. Commit it together with the task it ticks (see Commits).

## Commits

- Commit after **every** finished checklist task, never several tasks in one commit.
- Order per task: finish the code, run `uv run pytest` and `uv run ruff check` (once they exist) and make them pass, tick the task in `sprint/progress/NN.md`, then commit both.
- Message: Conventional Commits, `<type>(<version>/<step id>): <what changed>`, e.g. `feat(0.2.0/103): reject approve from todo`. The version is the one the step's sprint belongs to (`sprint/README.md` → Sprints). Types: feat, fix, test, refactor, docs, chore, ci.
- Never commit broken tests. If a task can't pass yet, split it.
- Never push. Never amend or rebase commits already made in a step.

## Never write these for Anis

The README pitch, the README state-machine section, and the "Decision" and "Why" parts of ADRs in `docs/decisions/`. Write questions or options for them, leave a `TODO(Anis)` marker, and list them in the step report.

## Versions

sprint-hub uses semver. `0.1.0` = v1 (`main`, tag `v0.1.0`). Planned: `0.2.0` core loop, `0.3.0` daily use, `0.4.0` away from the laptop, `1.0.0` insight (`docs/ROADMAP.md`).
- `pyproject.toml` holds `<next version>.dev0` while a version is being built (e.g. `0.2.0.dev0`).
- When Anis approves the last step of a version: set the plain version in `pyproject.toml`, commit `chore(<version>): release <version>`, and tag it `v<version>` (annotated). Never push the tag unless Anis asks.
