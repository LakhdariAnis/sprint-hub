"""`hubd import`: one vault step per spec in the repos. Reads repos, writes only in the vault."""

import re
import sys
from pathlib import Path

import frontmatter
import yaml

from hubd.daemon import vault_path
from hubd.model import Project, State

# `api-fields.md` or `design4-mock-list.md` sit next to the specs and are not steps.
_SPEC = re.compile(r"^(?P<id>[a-z]?\d+[a-z]?)-.+\.md$")
_TITLE = re.compile(r"^# Step \S+ — (?P<title>.+?)\s*$", re.M)
BODY = "## Runs\n\n## Review\nverdict:\ncomment:\n\n## Questions\n"


def specs(repo: Path) -> dict[str, Path]:
    """Step id -> spec; `sprint/` wins over the archive, like `vault._join`."""
    found: dict[str, Path] = {}
    for pattern in ("*.md", "archive/*/*.md"):
        for path in sorted((repo / "sprint").glob(pattern)):
            if m := _SPEC.match(path.name):
                found.setdefault(m["id"], path)
    return found


def model_of(repo: Path, step_id: str) -> str | None:
    commands = [repo / ".claude/commands" / f"sprint-{step_id}.md"]
    commands += sorted((repo / "sprint").glob(f"archive/**/commands/sprint-{step_id}.md"))
    path = next((p for p in commands if p.is_file()), None)
    if path is None:
        return None
    try:
        model = frontmatter.load(path).metadata.get("model")
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"warning: {path}: {exc}", file=sys.stderr)
        return None
    return model if isinstance(model, str) else None


def write_step(path: Path, meta: dict[str, object]) -> None:
    text = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    # "x": a step file is never overwritten, whatever happened since the exists() check.
    with path.open("x") as f:
        f.write(f"---\n{text}---\n\n{BODY}")


def import_project(folder: Path, project: Project, repo: Path) -> str:
    new = kept = 0
    for step_id, spec in specs(repo).items():
        target = folder / "steps" / f"{step_id}.md"
        if target.exists():
            kept += 1
            continue
        try:
            m = _TITLE.search(spec.read_text())
        except (OSError, ValueError) as exc:
            print(f"warning: {project.name}: {spec}: {exc}", file=sys.stderr)
            continue
        if not m:
            print(f"warning: {project.name}: {spec}: no '# Step <id> — <title>'", file=sys.stderr)
            continue
        meta: dict[str, object] = {"step": step_id, "title": m["title"], "state": State.todo.value}
        meta["by"] = "claude"
        if model := model_of(repo, step_id):
            meta["model"] = model
        meta["branch"] = f"step/{spec.stem}"
        write_step(target, meta)
        new += 1
    return f"{project.name}: {new} new, {kept} kept"


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
