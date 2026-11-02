import json
from pathlib import Path

import pytest

from hubd import doctor, install

THEME = Path(__file__).parent / "fixtures" / "theme" / "colors.toml"

HELP = """Usage: claude [options] [command] [prompt]
  --model <model>        Model for the current session.
  --session-id <uuid>    Use a specific session ID
  -r, --resume [value]   Resume a conversation
"""


@pytest.fixture(autouse=True)
def vault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An empty vault, never the real ~/Hub; a terminal every PATH below has."""
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "hub.toml").write_text('terminal = ["claude"]\n')
    monkeypatch.setenv("HUB_VAULT", str(vault))
    return vault


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


@pytest.fixture(autouse=True)
def no_systemctl(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor.service, "state", lambda: "not installed")


def settings(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps(data))
    return path


def test_all_good(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    fake_claude(tmp_path, monkeypatch, HELP)
    path = settings(tmp_path, install.with_hook({}))
    assert doctor.main(path, THEME) == 0
    out = capsys.readouterr().out.splitlines()
    assert out.pop() == "ℹ hubd service: not installed"  # info line, never a failure
    assert all(line.startswith("✔") for line in out)
    assert "✔ version 9.9.9 (Claude Code)" in out
    assert len(out) == 8  # path, version, 3 flags, hook, theme, terminal


def test_missing_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    fake_claude(tmp_path, monkeypatch, HELP.replace("--session-id", "--session"))
    assert doctor.main(settings(tmp_path, install.with_hook({})), THEME) == 1
    out = capsys.readouterr().out
    assert "✘ flag --session-id missing from claude --help" in out
    assert "✔ flag --model in claude --help" in out


def test_no_claude_and_no_hook(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))
    assert doctor.main(tmp_path / "missing.json", tmp_path / "colors.toml") == 1
    assert capsys.readouterr().out.splitlines() == [
        "✘ claude not on PATH",
        "✘ SessionEnd hook missing: run hubd install-hook",
        f"✘ theme {tmp_path / 'colors.toml'} not found: the app uses its default colours",
        "✘ terminal claude not on PATH",
        "ℹ hubd service: not installed",
    ]


def test_service_info_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    fake_claude(tmp_path, monkeypatch, HELP)
    path = settings(tmp_path, install.with_hook({}))
    assert doctor.main(path, THEME, lambda: "failed") == 0
    assert "ℹ hubd service: failed" in capsys.readouterr().out


def test_claude_that_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    fake_claude(tmp_path, monkeypatch, HELP)
    (tmp_path / "bin" / "claude").write_text("#!/bin/sh\nexit 3\n")
    assert doctor.main(tmp_path / "missing.json", THEME) == 1
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


def add_step(vault: Path, step: str, state: str = "todo") -> Path:
    repo = vault / "repo"
    (repo / ".claude" / "commands").mkdir(parents=True, exist_ok=True)
    folder = vault / "projects" / "try"
    (folder / "steps").mkdir(parents=True, exist_ok=True)
    (folder / "project.md").write_text(
        "---\nname: try\nrepo: repo\nmodel: haiku\nmerge: manual\n---\n"
    )
    (folder / "steps" / f"{step}.md").write_text(
        f"---\nstep: {step}\ntitle: Note\nstate: {state}\nby: claude\n---\n"
    )
    return repo / ".claude" / "commands"


def test_todo_steps_need_their_command(vault: Path) -> None:
    commands = add_step(vault, "901")
    add_step(vault, "902", "approved")  # no longer starts: needs no command
    assert doctor._commands(vault) == [(False, f"try: no command in {commands} for 901")]
    (commands / "sprint-901.md").write_text("Go\n")
    assert doctor._commands(vault) == [(True, "try: command for each of 1 todo steps")]


def test_terminal(vault: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))
    assert doctor._terminal(vault) == (False, "terminal claude not on PATH")
    (vault / "hub.toml").write_text("terminal = [")
    assert doctor._terminal(vault)[1].startswith("cannot read the terminal")
