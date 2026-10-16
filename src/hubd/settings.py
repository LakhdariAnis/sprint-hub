"""`~/Hub/hub.toml`: hubd settings. A missing file means all defaults."""

import tomllib
from pathlib import Path

from pydantic import BaseModel


class Settings(BaseModel):
    # argv that opens a terminal in `{cwd}`; the claude command is appended to it.
    terminal: list[str] = ["xdg-terminal-exec", "--dir={cwd}"]


def load_settings(path: Path) -> Settings:
    if not path.is_file():
        return Settings()
    return Settings.model_validate(tomllib.loads(path.read_text()))
