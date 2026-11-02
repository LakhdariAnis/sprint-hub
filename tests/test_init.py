import os
import subprocess
import sys
from pathlib import Path

import pytest

from hubd import init
from hubd.vault import load_vault


@pytest.fixture
def vault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "Hub"
    monkeypatch.setenv("HUB_VAULT", str(path))
    return path


def config(tmp_path: Path, *projects: tuple[str, object]) -> Path:
    path = tmp_path / "projects.toml"
    path.write_text(
        "".join(f'[[project]]\nname = "{name}"\npath = "{repo}"\n' for name, repo in projects)
    )
    return path


def repo(tmp_path: Path, name: str = "repo") -> Path:
    path = tmp_path / name
    path.mkdir()
    return path


def test_fresh_run_creates_every_project(
    vault: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    a, b = repo(tmp_path, "a"), repo(tmp_path, "b")

    assert init.main(config(tmp_path, ("BenWhispers", a), ("sprint-hub v2", b))) == 0

    assert capsys.readouterr().out.count("created") == 2
    assert (vault / "projects/benwhispers/steps").is_dir()
    assert list((vault / "projects/sprint-hub-v2/steps").iterdir()) == []
    index = load_vault(vault)
    assert index.errors == []
    assert set(index.projects) == {"benwhispers", "sprint-hub-v2"}
    project = index.projects["sprint-hub-v2"]
    assert (project.name, project.repo, project.model) == ("sprint-hub v2", b, "sonnet")
    assert project.merge == "manual"


def test_second_run_changes_nothing(
    vault: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    toml = config(tmp_path, ("demo", repo(tmp_path)))
    init.main(toml)
    project = vault / "projects/demo/project.md"
    before = project.stat().st_mtime_ns
    capsys.readouterr()

    assert init.main(toml) == 0

    out = capsys.readouterr().out
    assert "already exists" in out
    assert "created" not in out
    assert project.stat().st_mtime_ns == before


def test_edited_project_is_left_untouched(vault: Path, tmp_path: Path) -> None:
    toml = config(tmp_path, ("demo", repo(tmp_path)))
    init.main(toml)
    project = vault / "projects/demo/project.md"
    project.write_text(project.read_text() + "hello\n")

    init.main(toml)

    assert project.read_text().endswith("hello\n")


def test_project_missing_from_toml_stays_in_vault(vault: Path, tmp_path: Path) -> None:
    old = vault / "projects/old/project.md"
    old.parent.mkdir(parents=True)
    old.write_text("mine\n")

    assert init.main(config(tmp_path, ("demo", repo(tmp_path)))) == 0

    assert old.read_text() == "mine\n"


def test_missing_project_path_warns_and_keeps_going(
    vault: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    toml = config(tmp_path, ("gone", tmp_path / "gone"), ("demo", repo(tmp_path)))

    assert init.main(toml) == 0

    assert "warning: gone" in capsys.readouterr().err
    assert not (vault / "projects/gone").exists()
    assert (vault / "projects/demo/project.md").is_file()


def test_vault_that_cannot_be_created_exits_1(
    vault: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    vault.write_text("a file, not a folder")

    assert init.main(config(tmp_path, ("demo", repo(tmp_path)))) == 1

    assert "hubd init:" in capsys.readouterr().err


def test_missing_toml_is_one_line_error_and_creates_nothing(
    vault: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert init.main(tmp_path / "nope.toml") == 1

    err = capsys.readouterr().err
    assert "nope.toml" in err
    assert err.count("\n") == 1
    assert not vault.exists()


@pytest.mark.parametrize(
    "text",
    [
        "not toml at all",
        "",
        "project = 1",
        "project = [1]",
        '[[project]]\nname = "no path"\n',
        '[[project]]\npath = "/no/name"\n',
        '[[project]]\nname = 1\npath = "/x"\n',
        '[[project]]\nname = ""\npath = "/x"\n',
        '[[project]]\nname = "../out"\npath = "/x"\n',
        '[[project]]\nname = ".."\npath = "/x"\n',
        '[[project]]\nname = "Same Name"\npath = "/x"\n'
        '[[project]]\nname = "same-name"\npath = "/y"\n',
    ],
)
def test_broken_toml_is_one_line_error_and_creates_nothing(
    vault: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str], text: str
) -> None:
    toml = tmp_path / "projects.toml"
    toml.write_text(text)

    assert init.main(toml) == 1

    err = capsys.readouterr().err
    assert str(toml) in err
    assert err.count("\n") == 1
    assert not vault.exists()


def test_command_expands_tilde_and_honours_hub_vault(tmp_path: Path) -> None:
    (tmp_path / "work/demo").mkdir(parents=True)
    toml = tmp_path / ".config/sprint-hub/projects.toml"
    toml.parent.mkdir(parents=True)
    toml.write_text('[[project]]\nname = "demo"\npath = "~/work/demo"\n')
    vault = tmp_path / "elsewhere"

    result = subprocess.run(
        [sys.executable, "-m", "hubd", "init"],
        env=os.environ | {"HOME": str(tmp_path), "HUB_VAULT": str(vault)},
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert f"repo: {tmp_path}/work/demo\n" in (vault / "projects/demo/project.md").read_text()
