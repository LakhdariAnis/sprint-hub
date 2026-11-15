import json
from pathlib import Path

import pytest

from hubd import install

OTHER = {"type": "command", "command": "notify-send bye"}


def test_install_twice_gives_one_entry() -> None:
    once = install.with_hook({})
    assert install.with_hook(once) == once
    ours = [{"hooks": [{"type": "command", "command": install.COMMAND}]}]
    assert once == {"hooks": {"SessionEnd": ours, "Stop": ours, "Notification": ours}}


def test_install_keeps_other_settings_and_hooks() -> None:
    hooks = {"SessionEnd": [{"hooks": [OTHER]}], "Stop": [{"hooks": [OTHER]}], "PreToolUse": []}
    settings = {"model": "opus", "hooks": hooks}
    new = install.with_hook(settings)
    assert new["model"] == "opus"
    assert new["hooks"]["PreToolUse"] == []
    assert new["hooks"]["SessionEnd"][0] == {"hooks": [OTHER]}
    assert new["hooks"]["Stop"][0] == {"hooks": [OTHER]}
    assert all(install.installed(new, event) for event in install.EVENTS)
    assert settings["hooks"]["SessionEnd"] == [{"hooks": [OTHER]}]  # input not changed


def test_install_replaces_entry_from_another_venv() -> None:
    old = {"type": "command", "command": "/old/venv/bin/python -m hubd.hook"}
    new = install.with_hook({"hooks": {"SessionEnd": [{"hooks": [old]}]}})
    for event in install.EVENTS:
        commands = [h["command"] for g in new["hooks"][event] for h in g["hooks"]]
        assert commands == [install.COMMAND]


def test_uninstall_removes_only_ours() -> None:
    mine = {"SessionEnd": [{"hooks": [OTHER]}], "Notification": [{"hooks": [OTHER]}]}
    settings = install.with_hook({"hooks": mine})
    assert install.uninstalled(settings) == {"hooks": mine}
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
