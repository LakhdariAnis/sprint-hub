"""Load the vault into an in-memory index (docs/HUB-DESIGN.md section 4)."""

import os
import re
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
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
_FIELD = re.compile(r"^(?P<key>\w+):(?P<rest>.*?)(?P<eol>\r?)$")
_FRONTMATTER_FIELDS = ("state", "by", "model", "branch", "needs", "due")


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
    # When hubd saw each task (by text) reach its state; only changes seen while it runs.
    seen: dict[str, datetime | None] = field(default_factory=dict)


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


def format_run(run: Run) -> str:
    """The inverse of `parse_run`; minute precision, like the file."""
    parts = [f"{run.started:%Y-%m-%d %H:%M}", run.model, f"session {run.session}"]
    if run.minutes is not None:
        parts.append(f"{run.minutes} min")
    if run.tokens is not None:
        parts.append(f"{run.tokens} tokens")
    parts.append(f"task {run.task}")
    return "- " + " · ".join(parts)


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
    if not (path / "projects").is_dir():
        index.errors.append(FileError(path / "projects", None, "no projects folder"))
        return index
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


def save_step(path: Path, step: Step) -> None:
    """Write the changed frontmatter fields of `step` back to `path`; every other byte stays."""
    current = _load_step(path)
    lines = path.read_bytes().decode().split("\n")
    if lines[0].rstrip() != "---":
        raise ValueError(f"{path}: no frontmatter")
    end = next(i for i, line in enumerate(lines[1:], 1) if line.rstrip() == "---")
    eol = "\r" if lines[0].endswith("\r") else ""
    changed = {
        name: _format(getattr(step, name))
        for name in _FRONTMATTER_FIELDS
        if getattr(step, name) != getattr(current, name)
    }
    _set_fields(lines, 1, end, changed, eol)
    if step.runs != current.runs:
        _save_runs(lines, current.runs, step.runs, eol)
    if step.review and step.review != current.review:
        _save_review(lines, step.review, eol)
    _write_atomic(path, "\n".join(lines).encode())


def _save_runs(lines: list[str], old: list[Run], new: list[Run], eol: str) -> None:
    """Append the runs in `new` after `old`; existing run lines are never rewritten."""
    if new[: len(old)] != old:
        raise ValueError("runs can only be appended")
    added = [format_run(run) + eol for run in new[len(old) :]]
    heading = _find_heading(lines, "Runs")
    if heading is None:
        at = _find_heading(lines, "Review")
        if at is None:
            at = len(lines) - 1 if lines[-1] == "" else len(lines)
        lines[at:at] = [f"## Runs{eol}", *added, eol]
        return
    at = heading + 1
    for i in range(heading + 1, len(lines)):
        if _HEADING.match(lines[i]):
            break
        if lines[i].startswith("- "):
            at = i + 1
    lines[at:at] = added


def _find_heading(lines: list[str], name: str) -> int | None:
    return next(
        (i for i, line in enumerate(lines) if (m := _HEADING.match(line)) and m[1] == name), None
    )


def _save_review(lines: list[str], review: Review, eol: str) -> None:
    if "\n" in review.comment:
        raise ValueError("review comment must be one line")
    values = {"verdict": review.verdict or "", "comment": review.comment}
    heading = _find_heading(lines, "Review")
    if heading is None:
        at = len(lines) - 1 if lines[-1] == "" else len(lines)
        fields = [f"{k}: {v}".rstrip() + eol for k, v in values.items()]
        lines[at:at] = ["", f"## Review{eol}", *fields]
        return
    end = next((i for i in range(heading + 1, len(lines)) if _HEADING.match(lines[i])), len(lines))
    _set_fields(lines, heading + 1, end, values, eol)


def _format(value: object) -> str | None:
    """A field value as it is written in the file; None = remove the line."""
    if value is None:
        return None
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, list):
        return "[" + ", ".join(map(str, value)) + "]"
    return str(value)


def _set_fields(
    lines: list[str], start: int, end: int, values: dict[str, str | None], eol: str
) -> None:
    """Set `key: value` lines in `lines[start:end]` in place; keeps spacing and `# ...` comments."""
    for key, value in values.items():
        for i in range(start, end):
            m = _FIELD.match(lines[i])
            if m and m["key"] == key:
                break
        else:
            if value:
                at = end
                while at > start and not lines[at - 1].strip():
                    at -= 1
                lines.insert(at, f"{key}: {value}{eol}")
                end += 1
            continue
        if value is None:
            del lines[i]
            end -= 1
            continue
        rest = m["rest"]
        comment = c[0] if (c := _COMMENT.search(rest)) else ""
        lead = rest[: len(rest) - len(rest.lstrip())] or " "
        lines[i] = f"{key}:{lead if value else ''}{value}{comment}{m['eol']}"


def _write_atomic(path: Path, data: bytes) -> None:
    """Write to a temp file in the same folder, then rename over `path`."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f"{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        shutil.copymode(path, tmp)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


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
        # python-frontmatter keeps the newline after `---`, so the 0-based mark + 1 = file line
        return FileError(path, exc.problem_mark.line + 1, f"bad YAML: {exc.problem}")
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
