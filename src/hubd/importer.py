"""`hubd import`: one vault step per spec in the repos. Reads repos, writes only in the vault."""

import re
import subprocess
import sys
from pathlib import Path

import frontmatter
import yaml

from hubd.model import Project, State, TaskState
from hubd.vault import (
    _archive_sprint,
    _load_step,
    command_field,
    parse_tasks,
    save_step,
    split_sections,
    vault_path,
)

# `api-fields.md` or `design4-mock-list.md` sit next to the specs and are not steps.
_SPEC = re.compile(r"^(?P<id>[a-z]?\d+[a-z]?)-.+\.md$")
_TITLE = re.compile(r"^# Step \S+ — (?P<title>.+?)\s*$", re.M)
_SPRINT_TABLE = re.compile(r"^Sprint (\d+) — steps$")
_ROW = re.compile(r"^\|\s*`?(\w+)`?\s*\|")
BODY = "## Runs\n\n## Review\nverdict:\ncomment:\n\n## Questions\n"


def step_id(spec: Path) -> str | None:
    """`sprint/213a-x.md` -> `213a`; None when the file is not a spec."""
    m = _SPEC.match(spec.name)
    return m["id"] if m else None


def specs(repo: Path) -> dict[str, Path]:
    """Step id -> spec; `sprint/` wins over the archive, like `vault._join`."""
    found: dict[str, Path] = {}
    for pattern in ("*.md", "archive/*/*.md"):
        for path in sorted((repo / "sprint").glob(pattern)):
            if m := _SPEC.match(path.name):
                found.setdefault(m["id"], path)
    return found


def git(repo: Path, *args: str) -> str:
    """Read-only git; empty when `repo` is not a git repo or `ref` is missing."""
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else ""


def main_line(repo: Path) -> str | None:
    """`origin/HEAD` names it (sprint-hub: `v2`, its `main` is v1); else `main`, `master`."""
    remote = git(repo, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    for ref in (remote.removeprefix("origin/"), remote, "main", "master"):
        if ref and git(repo, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"):
            return ref
    return None


def step_branches(repo: Path) -> list[str]:
    return git(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads/step/").split()


def merged_branches(repo: Path, base: str) -> set[str]:
    # A project.md without `base:` on a repo with no `main`: fall back on the repo's own main line.
    has_base = git(repo, "rev-parse", "--verify", "--quiet", f"{base}^{{commit}}")
    line = base if has_base else main_line(repo)
    if line is None:
        return set()
    tip = git(repo, "rev-parse", line)
    fmt = "--format=%(refname:short) %(objectname)"
    rows = git(repo, "for-each-ref", f"--merged={line}", fmt, "refs/heads/step/").splitlines()
    # A branch still at the tip has no work of its own yet: not merged.
    return {name for name, sha in map(str.split, rows) if sha != tip}


def pushed_branches(repo: Path, base: str) -> set[str]:
    """Step branches whose work is in a remote branch: pushed to GitHub means Anis reviewed it."""
    full = "--format=%(refname) %(objectname)"
    refs = git(repo, "for-each-ref", full, "refs/remotes/").splitlines()
    remotes = [ref for ref, _ in map(str.split, refs) if not ref.endswith("/HEAD")]
    # A step branch still at the tip of a main line (local or remote) has no work of its own yet.
    lines = [ref for ref in remotes if "/step/" not in ref]
    tips = {git(repo, "rev-parse", ref) for ref in [*lines, base, main_line(repo) or ""] if ref}
    fmt = "--format=%(refname:short) %(objectname)"
    pushed: set[str] = set()
    for ref in remotes:
        rows = git(repo, "for-each-ref", f"--merged={ref}", fmt, "refs/heads/step/").splitlines()
        pushed |= {name for name, sha in map(str.split, rows) if sha not in tips}
    return pushed


def archived(repo: Path, spec: Path) -> bool:
    """A spec under `sprint/archive/` belongs to a closed sprint."""
    return spec.relative_to(repo / "sprint").parts[0] == "archive"


def progress_merged(repo: Path) -> set[str]:
    """Step ids whose `## date — Step <id> ...` entry in PROGRESS.md says "Merged"."""
    path = repo / "sprint/PROGRESS.md"
    if not path.is_file():
        return set()
    merged = set()
    # Case matters: "not merged yet" appears in entries of steps that are not merged.
    for block in re.split(r"(?m)^## ", path.read_text(errors="replace"))[1:]:
        m = re.search(r"Step (\w+)", block.partition("\n")[0])
        if m and "Merged" in block:
            merged.add(m[1].lower())
    return merged


def all_ticked(repo: Path, step_id: str) -> bool:
    paths = [repo / "sprint/progress" / f"{step_id}.md"]
    paths += sorted((repo / "sprint").glob(f"archive/**/progress/{step_id}.md"))
    path = next((p for p in paths if p.is_file()), None)
    tasks = parse_tasks(path.read_text()) if path else []
    return bool(tasks) and all(t.state == TaskState.done for t in tasks)


def state_of(repo: Path, step_id: str, approved: bool) -> State:
    if approved:
        return State.approved
    return State.done if all_ticked(repo, step_id) else State.todo


def sprint_tables(repo: Path) -> dict[str, int]:
    """Step id -> sprint, from the `## Sprint <n> — steps` tables of both READMEs."""
    sprints: dict[str, int] = {}
    for path in (repo / "sprint/README.md", repo / "sprint/archive/README.md"):
        if not path.is_file():
            continue
        for heading, lines in split_sections(path.read_text(errors="replace")).items():
            if m := _SPRINT_TABLE.match(heading):
                for row in filter(None, map(_ROW.match, lines)):
                    sprints.setdefault(row[1], int(m[1]))
    return sprints


def model_of(repo: Path, step_id: str) -> str | None:
    return command_field(repo, step_id, "model")


def write_step(path: Path, meta: dict[str, object]) -> None:
    text = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    # "x": a step file is never overwritten, whatever happened since the exists() check.
    with path.open("x") as f:
        f.write(f"---\n{text}---\n\n{BODY}")


def import_project(folder: Path, project: Project, repo: Path, only: Path | None = None) -> str:
    """Write the missing step files of a project; `only` limits it to one spec file.

    A step file already there is kept, except a `todo` or `done` one that is now known reviewed: it
    becomes `approved`.
    """
    new = kept = upgraded = 0
    logged = progress_merged(repo)
    branches = step_branches(repo)
    merged = merged_branches(repo, project.base) | pushed_branches(repo, project.base)
    sprints = sprint_tables(repo)
    no_sprint: list[str] = []
    for step_id, spec in specs(repo).items():
        if only and spec != only:
            continue
        target = folder / "steps" / f"{step_id}.md"
        mine = [b for b in branches if b.startswith(f"step/{step_id}-")]
        approved = archived(repo, spec) or step_id in logged or any(b in merged for b in mine)
        if target.exists():
            kept += 1
            upgraded += approve_kept(target) if approved else 0
            continue
        try:
            m = _TITLE.search(spec.read_text())
            state = state_of(repo, step_id, approved)
        except (OSError, ValueError) as exc:
            print(f"warning: {project.name}: {spec}: {exc}", file=sys.stderr)
            continue
        if not m:
            print(f"warning: {project.name}: {spec}: no '# Step <id> — <title>'", file=sys.stderr)
            continue
        meta: dict[str, object] = {"step": step_id, "title": m["title"], "state": state.value}
        meta["by"] = "claude"
        if model := model_of(repo, step_id):
            meta["model"] = model
        # The real branch when its slug differs from the spec's: approve merges this name.
        branch = f"step/{spec.stem}"
        meta["branch"] = branch if branch in mine or not mine else mine[0]
        if sprint := sprints.get(step_id) or _archive_sprint(spec):
            meta["sprint"] = sprint
        else:
            no_sprint.append(step_id)
        write_step(target, meta)
        new += 1
    listed = f" ({', '.join(no_sprint)})" if no_sprint else ""
    return (
        f"{project.name}: {new} new, {kept} kept, {upgraded} now approved,"
        f" {len(no_sprint)} no sprint{listed}"
    )


def approve_kept(path: Path) -> int:
    """Set a kept `todo` / `done` step to `approved`; 1 when it changed. Broken file: left alone."""
    try:
        step = _load_step(path)
        if step.state not in (State.todo, State.done):
            return 0
        save_step(path, step.model_copy(update={"state": State.approved}))
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"warning: {path}: {exc}", file=sys.stderr)
        return 0
    return 1


def main(only: str | None = None) -> int:
    projects = vault_path() / "projects"
    folders = sorted(p for p in projects.glob("*") if (p / "project.md").is_file())
    if not folders:
        print(f"hubd import: no projects in {projects}, run hubd init first", file=sys.stderr)
        return 1
    matched = False
    try:
        for folder in folders:
            try:
                project = Project.model_validate(frontmatter.load(folder / "project.md").metadata)
            except (OSError, ValueError, yaml.YAMLError) as exc:
                print(f"warning: {folder / 'project.md'}: {exc}", file=sys.stderr)
                continue
            if only not in (None, folder.name, project.name):
                continue
            matched = True
            repo = vault_path() / project.repo if project.repo else None
            if repo is None or not repo.is_dir():
                print(f"warning: {project.name}: repo {repo} not found, skipped", file=sys.stderr)
                continue
            print(import_project(folder, project, repo))
    except OSError as exc:
        print(f"hubd import: {exc}", file=sys.stderr)
        return 1
    if only and not matched:
        print(f"hubd import: no project {only!r}", file=sys.stderr)
        return 1
    return 0
