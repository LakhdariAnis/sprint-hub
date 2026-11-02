"""`~/Hub/hub.toml`: hubd settings. A missing file means all defaults."""

import json
import tomllib
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ValidationError, field_validator

from hubd.vault import _write_atomic


class Settings(BaseModel):
    # argv that opens a terminal in `{cwd}`; the claude command is appended to it.
    terminal: list[str] = ["xdg-terminal-exec", "--dir={cwd}"]
    # Deadline reminders are sent from this hour on (local time), never earlier that day.
    reminder_hour: int = 9

    @field_validator("terminal")
    @classmethod
    def _cwd(cls, argv: list[str]) -> list[str]:
        if not any("{cwd}" in arg for arg in argv):
            raise ValueError("must contain {cwd}, the folder the terminal opens in")
        return argv

    @field_validator("reminder_hour")
    @classmethod
    def _hour(cls, hour: int) -> int:
        if not 0 <= hour <= 23:
            raise ValueError("must be 0–23")
        return hour


@dataclass
class Current:
    """What hubd runs with now. `error`: why hub.toml could not be read, so these are defaults."""

    settings: Settings
    error: str | None = None


def reason(exc: ValidationError) -> str:
    """`reminder_hour: must be 0–23`, one line per bad field."""
    return "; ".join(
        f"{'.'.join(map(str, e['loc']))}: {str(e['msg']).removeprefix('Value error, ')}"
        for e in exc.errors()
    )


def load_settings(path: Path) -> Settings:
    if not path.is_file():
        return Settings()
    return Settings.model_validate(tomllib.loads(path.read_text()))


def load_current(path: Path) -> Current:
    """Like `load_settings`, but a file that does not parse gives defaults and the reason."""
    try:
        return Current(load_settings(path))
    except ValidationError as exc:
        return Current(Settings(), f"{path}: {reason(exc)}")
    except (OSError, ValueError) as exc:  # TOMLDecodeError, bad UTF-8
        return Current(Settings(), f"{path}: {exc}")


def has_comments(path: Path) -> bool:
    """A save rewrites the file from the two settings: comments and other keys go."""
    try:
        return "#" in path.read_text()
    except OSError:
        return False


def save_settings(path: Path, settings: Settings) -> None:
    # JSON strings are TOML strings for what a terminal argv holds.
    text = f"terminal = {json.dumps(settings.terminal)}\nreminder_hour = {settings.reminder_hour}\n"
    if path.exists():
        _write_atomic(path, text.encode())
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
