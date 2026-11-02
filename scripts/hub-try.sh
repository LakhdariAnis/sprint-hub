#!/usr/bin/env bash
# A throwaway repo and vault project for trying real runs: ~/tmp/hub-try, project hub-try, steps 901-903.
# `scripts/hub-try.sh --remove` deletes both. Starts nothing: a run only begins when you press `s`.
set -euo pipefail
cd "$(dirname "$0")/.."
repo=$HOME/tmp/hub-try
project=${HUB_VAULT:-$HOME/Hub}/projects/hub-try

if [ "${1:-}" = --remove ]; then
  rm -rf "$repo" "$project"
  echo "removed $repo and $project"
  exit 0
fi
if [ -e "$repo" ] || [ -e "$project" ]; then
  echo "hub-try.sh: $repo or $project exists; run scripts/hub-try.sh --remove first" >&2
  exit 1
fi

mkdir -p "$repo/sprint" "$repo/.claude/commands" "$project/steps"
git -C "$repo" init -q -b main
git -C "$repo" config user.name "hub-try"
git -C "$repo" config user.email "hub-try@hubd.invalid"
printf 'sprint/\n.claude/commands/\n' >"$repo/.gitignore"
cat >"$repo/CLAUDE.md" <<'MD'
# hub-try

A throwaway repo for trying sprint-hub runs. Do only what the step asks.

## Checklist

When working on a step, write `sprint/progress/NN.md` (NN = step id) before the first edit. First line `# Step NN`, then one line `- [ ] <task>` per task in the step file. Mark the task you are on `- [~]` (only one at a time) and change it to `- [x]` as soon as it is done. Edit the file right away, not in a batch at the end: sprint-hub shows it live.

`sprint/` and `.claude/commands/` are gitignored: never commit them.

## Commits

Commit after every finished task, on the step's branch. Never push.
MD
git -C "$repo" add .
git -C "$repo" commit -q -m "hub-try: start"

add_step() { # id, slug, title, text file
  local spec="sprint/$1-$2.md"
  cat >"$repo/$spec" <<MD
# Step $1 — $3

Branch \`step/$1-$2\`, from \`main\`.

## Goal
Add the text file \`$4\`.

## Tasks
- Create branch \`step/$1-$2\` from \`main\`
- Add \`$4\` with one line saying which step wrote it, and commit it
MD
  cat >"$repo/.claude/commands/sprint-$1.md" <<MD
---
description: Sprint $1 - $3
model: haiku
---
Read \`CLAUDE.md\` and \`$spec\`, then do the step. When every task is done, say so and stop.
MD
}
add_step 901 first-note "Add the first note" first.txt
add_step 902 second-note "Add the second note" second.txt
add_step 903 third-note "Add the third note" third.txt

printf -- '---\nname: hub-try\nrepo: %s\nmodel: haiku\nmerge: manual\n---\n' "$repo" >"$project/project.md"
uv run hubd import hub-try
echo "created $repo and $project"
