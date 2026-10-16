"""Load the vault into an in-memory index (docs/HUB-DESIGN.md section 4)."""

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import frontmatter
import yaml
from pydantic import ValidationError

from hubd.model import Project, Review, Run, Step, Task

_HEADING = re.compile(r"^## (.+?)\s*$")
# ` # ...` after a value is a YAML-style comment, e.g. `verdict: changes  # approve | changes`.
# shortcut: a ` #` inside a review comment is cut too, use a real escape if that ever bites.
_COMMENT = re.compile(r"\s+#.*$")
_SIZE = {"k": 1_000, "M": 1_000_000}
_TASK = re.compile(r"^- \[(?P<mark>[ ~x])\] (?P<text>.+)$", re.M)


@dataclass
class FileError:
    path: Path
    line: int | None
    message: str


@dataclass
class StepEntry:
    """A vault step joined with its repo spec and live checklist."""

    project: str
    path: Path
    step: Step
    spec: Path | None = None
    tasks: list[Task] = field(default_factory=list)


@dataclass
class Index:
    projects: dict[str, Project] = field(default_factory=dict)
    steps: list[StepEntry] = field(default_factory=list)
    errors: list[FileError] = field(default_factory=list)


def split_sections(body: str) -> dict[str, list[str]]:
    """`## Name` heading -> the lines under it, up to the next `## ` heading."""
    sections: dict[str, list[str]] = {}
    lines: list[str] | None = None
    for line in body.splitlines():
        if m := _HEADING.match(line):
            lines = sections.setdefault(m[1], [])
        elif lines is not None:
            lines.append(line)
    return sections


def parse_run(line: str) -> Run:
    """`- 2026-10-15 22:10 · sonnet · session 7b1e…a04 · 42 min · 1.2M tokens · task all`."""
    started, model, *rest = (part.strip() for part in line.removeprefix("- ").split("·"))
    fields: dict[str, object] = {"started": started, "model": model}
    for part in rest:
        key, _, value = part.partition(" ")
        if key in ("session", "task"):
            fields[key] = value
        elif value == "min":
            fields["minutes"] = key
        elif value == "tokens":
            num, unit = (key[:-1], key[-1]) if key[-1] in _SIZE else (key, "")
            fields["tokens"] = round(float(num) * _SIZE.get(unit, 1))
        else:
            raise ValueError(f"unknown run field {part!r}")
    return Run.model_validate(fields)


def parse_review(lines: list[str]) -> Review:
    """`key: value` lines; an empty value means not set."""
    fields = {}
    for line in lines:
        key, sep, value = _COMMENT.sub("", line).partition(":")
        if sep and (value := value.strip()):
            fields[key.strip()] = value
    return Review.model_validate(fields)


def parse_body(body: str) -> tuple[list[Run], Review | None]:
    sections = split_sections(body)
    runs = [parse_run(line) for line in sections.get("Runs", []) if line.startswith("- ")]
    review = parse_review(sections["Review"]) if "Review" in sections else None
    return runs, review


def parse_tasks(text: str) -> list[Task]:
    return [Task(state=m["mark"], text=m["text"]) for m in _TASK.finditer(text)]


def load_vault(path: Path) -> Index:
    """Read every project and step under `path/projects`. A broken file becomes one FileError."""
    index = Index()
    for project_dir in sorted(p for p in (path / "projects").iterdir() if p.is_dir()):
        project = _guard(index, project_dir / "project.md", _load_project)
        if project:
            index.projects[project_dir.name] = project
        repo = path / project.repo if project and project.repo else None
        for step_path in sorted((project_dir / "steps").glob("*.md")):
            step = _guard(index, step_path, _load_step)
            if step:
                index.steps.append(_join(project_dir.name, step_path, step, repo))
    return index


def _load_project(path: Path) -> Project:
    return Project.model_validate(frontmatter.load(path).metadata)


def _load_step(path: Path) -> Step:
    post = frontmatter.load(path)
    meta = dict(post.metadata)
    # YAML reads `step: 02` as 2; the file name keeps the zero.
    if isinstance(meta.get("step"), int) and path.stem.isdigit() and int(path.stem) == meta["step"]:
        meta["step"] = path.stem
    meta["runs"], meta["review"] = parse_body(post.content)
    return Step.model_validate(meta)


def _join(project: str, path: Path, step: Step, repo: Path | None) -> StepEntry:
    entry = StepEntry(project=project, path=path, step=step)
    if repo:
        entry.spec = next(iter(sorted(repo.glob(f"sprint/{step.step}-*.md"))), None)
        progress = repo / "sprint" / "progress" / f"{step.step}.md"
        if progress.is_file():
            entry.tasks = parse_tasks(progress.read_text())
    return entry


def _guard[T](index: Index, path: Path, load: Callable[[Path], T]) -> T | None:
    """Run `load(path)`; on a broken file record one FileError and return None."""
    try:
        return load(path)
    except (OSError, yaml.YAMLError, ValueError) as exc:
        index.errors.append(_file_error(path, exc))
        return None


def _file_error(path: Path, exc: Exception) -> FileError:
    if isinstance(exc, yaml.MarkedYAMLError) and exc.problem_mark:
        # mark is 0-based inside the frontmatter, which starts after the `---` on line 1
        return FileError(path, exc.problem_mark.line + 2, f"bad YAML: {exc.problem}")
    if isinstance(exc, ValidationError):
        errors = exc.errors()
        first = errors[0]["loc"][0] if errors[0]["loc"] else None
        message = "; ".join(f"{'.'.join(map(str, e['loc'])) or 'file'}: {e['msg']}" for e in errors)
        return FileError(path, _field_line(path, first), message)
    return FileError(path, None, str(exc))


def _field_line(path: Path, name: object) -> int | None:
    """Line of `name:` in the file, or None if the field is missing."""
    for number, line in enumerate(path.read_text().splitlines(), 1):
        if line.startswith(f"{name}:"):
            return number
    return None
