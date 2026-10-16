import json
from pathlib import Path

import pytest

from hubd import doctor, install

HELP = """Usage: claude [options] [command] [prompt]
  --model <model>        Model for the current session.
  --session-id <uuid>    Use a specific session ID
  -r, --resume [value]   Resume a conversation
"""


def fake_claude(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, help_text: str) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    script = bin_dir / "claude"
    script.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = --version ]; then echo "9.9.9 (Claude Code)"; exit 0; fi\n'
        f"cat <<'EOF'\n{help_text}EOF\n"
    )
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:/usr/bin:/bin")  # the script needs cat


def settings(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps(data))
    return path


def test_all_good(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    fake_claude(tmp_path, monkeypatch, HELP)
    path = settings(tmp_path, install.with_hook({}))
    assert doctor.main(path) == 0
    out = capsys.readouterr().out.splitlines()
    assert all(line.startswith("✔") for line in out)
    assert "✔ version 9.9.9 (Claude Code)" in out
    assert len(out) == 6  # path, version, 3 flags, hook


def test_missing_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    fake_claude(tmp_path, monkeypatch, HELP.replace("--session-id", "--session"))
    assert doctor.main(settings(tmp_path, install.with_hook({}))) == 1
    out = capsys.readouterr().out
    assert "✘ flag --session-id missing from claude --help" in out
    assert "✔ flag --model in claude --help" in out


def test_no_claude_and_no_hook(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))
    assert doctor.main(tmp_path / "missing.json") == 1
    assert capsys.readouterr().out.splitlines() == [
        "✘ claude not on PATH",
        "✘ SessionEnd hook missing: run hubd install-hook",
    ]


def test_claude_that_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    fake_claude(tmp_path, monkeypatch, HELP)
    (tmp_path / "bin" / "claude").write_text("#!/bin/sh\nexit 3\n")
    assert doctor.main(tmp_path / "missing.json") == 1
    assert "✘ claude does not run" in capsys.readouterr().out


def test_hook_from_other_venv_and_broken_settings(tmp_path: Path) -> None:
    other = {"type": "command", "command": "/old/bin/python -m hubd.hook"}
    path = settings(tmp_path, {"hooks": {"SessionEnd": [{"hooks": [other]}]}})
    assert doctor._hook(path) == [
        (False, "SessionEnd hook points to another python: run hubd install-hook")
    ]
    path.write_text("{")
    [(ok, text)] = doctor._hook(path)
    assert not ok and text.startswith("cannot read")
