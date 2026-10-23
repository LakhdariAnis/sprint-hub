"""`~/Hub/hub.toml`: hubd settings. A missing file means all defaults."""

import tomllib
from pathlib import Path

from pydantic import BaseModel, Field


class Settings(BaseModel):
    # argv that opens a terminal in `{cwd}`; the claude command is appended to it.
    terminal: list[str] = ["xdg-terminal-exec", "--dir={cwd}"]
    # Deadline reminders are sent from this hour on (local time), never earlier that day.
    reminder_hour: int = Field(9, ge=0, le=23)


def load_settings(path: Path) -> Settings:
    if not path.is_file():
        return Settings()
    return Settings.model_validate(tomllib.loads(path.read_text()))
