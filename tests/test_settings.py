from pathlib import Path

import pytest
from pydantic import ValidationError

from hubd.settings import (
    Current,
    Settings,
    has_comments,
    load_current,
    load_settings,
    reason,
    save_settings,
)


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


def test_terminal_needs_cwd() -> None:
    Settings(terminal=["foot", "--working-directory={cwd}"])
    for argv in (["foot"], []):
        with pytest.raises(ValidationError, match=r"\{cwd\}"):
            Settings(terminal=argv)


def test_reminder_hour_message() -> None:
    with pytest.raises(ValidationError) as exc:
        Settings(reminder_hour=99)
    assert reason(exc.value) == "reminder_hour: must be 0–23"


def test_load_current_survives_a_broken_file(tmp_path: Path) -> None:
    path = tmp_path / "hub.toml"
    path.write_text("broken = [\n")
    cur = load_current(path)
    assert cur.settings == Settings()
    assert cur.error and str(path) in cur.error
    path.write_text("reminder_hour = 99\n")
    assert load_current(path).error.endswith("reminder_hour: must be 0–23")
    path.write_text("reminder_hour = 8\n")
    assert load_current(path) == Current(Settings(reminder_hour=8))


def test_save_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "hub.toml"
    new = Settings(terminal=["foot", "-D", "{cwd}", 'q"x'], reminder_hour=7)
    save_settings(path, new)
    assert load_settings(path) == new
    assert not has_comments(path)
    path.write_text("# mine\nreminder_hour = 8\n")
    assert has_comments(path)
    save_settings(path, new)
    assert load_settings(path) == new and not has_comments(path)
    assert [p.name for p in tmp_path.iterdir()] == ["hub.toml"]
