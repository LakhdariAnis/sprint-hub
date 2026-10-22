"""Typed models for the vault (docs/HUB-DESIGN.md section 4)."""

from datetime import date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict


class State(StrEnum):
    todo = "todo"
    doing = "doing"
    done = "done"
    changes = "changes"
    approved = "approved"


class Merge(StrEnum):
    auto = "auto"
    manual = "manual"


class TaskState(StrEnum):
    # value = the checkbox mark in sprint/progress/<id>.md
    todo = " "
    doing = "~"
    done = "x"


class Project(BaseModel):
    """`projects/<project>/project.md` frontmatter."""

    name: str
    repo: Path | None = None
    model: str
    merge: Merge


class Task(BaseModel):
    """One checklist line in `sprint/progress/<id>.md`."""

    text: str
    state: TaskState


class Run(BaseModel):
    """One line under `## Runs` in a vault step file."""

    started: datetime
    model: str
    session: str
    minutes: int | None = None
    tokens: int | None = None
    task: str = "all"


class Review(BaseModel):
    """The `## Review` section of a vault step file."""

    verdict: Literal["approve", "changes"] | None = None
    comment: str = ""


class Step(BaseModel):
    """`projects/<project>/steps/<id>.md`: frontmatter, plus runs and review from the body."""

    # YAML reads `step: 101` as an int; keep ids as strings.
    # `step: 02` loads as 2 (YAML drops the zero); the loader puts the zero back.
    model_config = ConfigDict(coerce_numbers_to_str=True)

    step: str
    title: str
    state: State
    by: Literal["claude", "me"] = "claude"
    model: str | None = None
    branch: str | None = None
    needs: list[str] = []
    sprint: int | None = None
    due: date | None = None
    runs: list[Run] = []
    review: Review | None = None
