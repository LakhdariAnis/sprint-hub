# sprint-hub v2

Branch `v2` is the rebuild described in `docs/HUB-DESIGN.md`. Branch `main` is the current sprint-hub: never change it from here.

## Checklist

When working on a sprint step, after the plan write `sprint/progress/NN.md` (NN = step id, e.g. `02`, `01a`) before the first edit. First line `# Step NN`, then one line `- [ ] <task>` per task in the step file. Mark the task you are on `- [~]` (only one at a time) and change it to `- [x]` as soon as it is done. Edit the file right away, not in a batch at the end: sprint-hub shows it live. Commit it with the step.
