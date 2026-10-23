from pathlib import Path

import pytest
from pydantic import ValidationError

from hubd.settings import Settings, load_settings


def test_missing_file_gives_defaults(tmp_path: Path) -> None:
    assert load_settings(tmp_path / "hub.toml") == Settings()
    assert Settings().terminal == ["xdg-terminal-exec", "--dir={cwd}"]


def test_terminal_from_file(tmp_path: Path) -> None:
    path = tmp_path / "hub.toml"
    path.write_text('terminal = ["foot", "--working-directory={cwd}"]\n')
    assert load_settings(path).terminal == ["foot", "--working-directory={cwd}"]


def test_wrong_type_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "hub.toml"
    path.write_text('terminal = "foot"\n')
    with pytest.raises(ValidationError):
        load_settings(path)


def test_reminder_hour(tmp_path: Path) -> None:
    path = tmp_path / "hub.toml"
    assert Settings().reminder_hour == 9
    path.write_text("reminder_hour = 7\n")
    assert load_settings(path).reminder_hour == 7
    path.write_text("reminder_hour = 24\n")
    with pytest.raises(ValidationError):
        load_settings(path)
