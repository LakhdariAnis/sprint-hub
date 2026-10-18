import json
from pathlib import Path

import pytest

from hubd import install

OTHER = {"type": "command", "command": "notify-send bye"}


def test_install_twice_gives_one_entry() -> None:
    once = install.with_hook({})
    assert install.with_hook(once) == once
    assert once == {
        "hooks": {"SessionEnd": [{"hooks": [{"type": "command", "command": install.COMMAND}]}]}
    }


def test_install_keeps_other_settings_and_hooks() -> None:
    settings = {"model": "opus", "hooks": {"SessionEnd": [{"hooks": [OTHER]}], "Stop": []}}
    new = install.with_hook(settings)
    assert new["model"] == "opus"
    assert new["hooks"]["Stop"] == []
    assert new["hooks"]["SessionEnd"][0] == {"hooks": [OTHER]}
    assert install.installed(new)
    assert settings["hooks"]["SessionEnd"] == [{"hooks": [OTHER]}]  # input not changed


def test_install_replaces_entry_from_another_venv() -> None:
    old = {"type": "command", "command": "/old/venv/bin/python -m hubd.hook"}
    new = install.with_hook({"hooks": {"SessionEnd": [{"hooks": [old]}]}})
    commands = [h["command"] for g in new["hooks"]["SessionEnd"] for h in g["hooks"]]
    assert commands == [install.COMMAND]


def test_uninstall_removes_only_ours() -> None:
    settings = install.with_hook({"hooks": {"SessionEnd": [{"hooks": [OTHER]}]}})
    assert install.uninstalled(settings) == {"hooks": {"SessionEnd": [{"hooks": [OTHER]}]}}
    assert install.uninstalled(install.with_hook({})) == {}
    assert install.uninstalled({}) == {}


def test_cli_asks_then_writes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / ".claude" / "settings.json"
    assert install.change(install.with_hook, path, ask=lambda _: "n") == 1
    assert not path.exists()
    assert install.change(install.with_hook, path, ask=lambda _: "y") == 0
    assert install.installed(json.loads(path.read_text()))
    assert "+" in capsys.readouterr().out  # the diff was shown

    def never(_: str) -> str:
        raise AssertionError("must not ask when nothing changes")

    assert install.change(install.with_hook, path, ask=never) == 0
    assert install.change(install.uninstalled, path, ask=lambda _: "y") == 0
    assert json.loads(path.read_text()) == {}


def test_no_terminal_means_no(tmp_path: Path) -> None:
    def eof(_: str) -> str:
        raise EOFError

    path = tmp_path / "settings.json"
    assert install.change(install.with_hook, path, ask=eof) == 1
    assert not path.exists()
