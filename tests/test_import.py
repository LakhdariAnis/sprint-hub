import os
import subprocess
import sys
from pathlib import Path

import pytest

from hubd import importer
from hubd.model import State
from hubd.vault import _load_step, load_vault


@pytest.fixture
def vault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "Hub"
    monkeypatch.setenv("HUB_VAULT", str(path))
    return path


@pytest.fixture
def repo(tmp_path: Path, vault: Path) -> Path:
    """A repo with a `sprint/` folder, registered in the vault as project `demo`."""
    path = tmp_path / "repo"
    (path / "sprint").mkdir(parents=True)
    add_project(vault, "demo", "Demo", path)
    return path


def add_project(vault: Path, slug: str, name: str, path: Path) -> None:
    folder = vault / "projects" / slug
    (folder / "steps").mkdir(parents=True)
    (folder / "project.md").write_text(
        f"---\nname: {name}\nrepo: {path}\nmodel: sonnet\nmerge: manual\n---\n"
    )


def spec(repo: Path, name: str, folder: str = "sprint") -> Path:
    path = repo / folder / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    step_id = name.partition("-")[0]
    path.write_text(f"# Step {step_id} — Title of {step_id}\n\nBody.\n")
    return path


def step_file(vault: Path, step_id: str, project: str = "demo") -> Path:
    return vault / "projects" / project / "steps" / f"{step_id}.md"


def test_writes_every_field_and_loads_clean(vault: Path, repo: Path) -> None:
    spec(repo, "101-first")
    commands = repo / ".claude/commands"
    commands.mkdir(parents=True)
    (commands / "sprint-101.md").write_text("---\ndescription: x\nmodel: opus\n---\nprompt\n")

    assert importer.main() == 0

    step = _load_step(step_file(vault, "101"))
    assert (step.step, step.title, step.by) == ("101", "Title of 101", "claude")
    assert (step.model, step.branch, step.state) == ("opus", "step/101-first", State.todo)
    text = step_file(vault, "101").read_text()
    assert "## Runs" in text and "## Review" in text and "## Questions" in text
    assert load_vault(vault).errors == []


def test_no_command_file_leaves_model_out(vault: Path, repo: Path) -> None:
    spec(repo, "101-first")

    importer.main()

    assert _load_step(step_file(vault, "101")).model is None


def test_broken_command_file_warns_and_leaves_model_out(
    vault: Path, repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    spec(repo, "101-first")
    commands = repo / ".claude/commands"
    commands.mkdir(parents=True)
    (commands / "sprint-101.md").write_text("---\nmodel: [\n---\n")

    assert importer.main() == 0

    assert "warning" in capsys.readouterr().err
    assert _load_step(step_file(vault, "101")).model is None


@pytest.mark.parametrize(
    "folder", ["sprint/archive/sprint-2", "sprint/archive/steps"], ids=["sprint-n", "steps"]
)
def test_archive_specs_and_commands(vault: Path, repo: Path, folder: str) -> None:
    spec(repo, "201-old", folder)
    commands = repo / folder.replace("/steps", "") / "commands"
    commands.mkdir(parents=True)
    (commands / "sprint-201.md").write_text("---\nmodel: haiku\n---\n")

    importer.main()

    step = _load_step(step_file(vault, "201"))
    assert (step.title, step.branch, step.model) == ("Title of 201", "step/201-old", "haiku")


@pytest.mark.parametrize("step_id", ["409b", "a901", "01a", "02"])
def test_id_shapes(vault: Path, repo: Path, step_id: str) -> None:
    spec(repo, f"{step_id}-x")

    importer.main()

    assert _load_step(step_file(vault, step_id)).step == step_id
    assert load_vault(vault).errors == []


def test_title_with_yaml_characters(vault: Path, repo: Path) -> None:
    (repo / "sprint/101-x.md").write_text("# Step 101 — `hubd`: a #1 title\n")

    importer.main()

    assert _load_step(step_file(vault, "101")).title == "`hubd`: a #1 title"


def test_other_files_in_sprint_are_not_steps(vault: Path, repo: Path) -> None:
    for name in ("api-fields", "design4-mock-list", "ros2-car-prompt", "README", "PROGRESS"):
        (repo / "sprint" / f"{name}.md").write_text("# Notes\n")

    assert importer.main() == 0

    assert list((vault / "projects/demo/steps").iterdir()) == []


def test_second_run_only_adds_new_steps(
    vault: Path, repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    spec(repo, "101-first")
    importer.main()
    edited = step_file(vault, "101")
    edited.write_text(edited.read_text().replace("state: todo", "state: doing") + "mine\n")
    capsys.readouterr()

    importer.main()
    assert "Demo: 0 new, 1 kept" in capsys.readouterr().out

    spec(repo, "102-second")
    importer.main()
    assert "Demo: 1 new, 1 kept" in capsys.readouterr().out
    assert edited.read_text().endswith("mine\n")
    assert _load_step(edited).state == State.doing


@pytest.mark.parametrize("data", [b"no title line\n", b"\xff\xfe not utf-8"], ids=["title", "utf8"])
def test_broken_spec_warns_and_the_rest_imports(
    vault: Path, repo: Path, capsys: pytest.CaptureFixture[str], data: bytes
) -> None:
    (repo / "sprint/101-broken.md").write_bytes(data)
    spec(repo, "102-good")

    assert importer.main() == 0

    captured = capsys.readouterr()
    assert "warning: Demo" in captured.err and "101-broken.md" in captured.err
    assert "Demo: 1 new, 0 kept" in captured.out
    assert not step_file(vault, "101").exists()


def test_only_the_named_project(vault: Path, repo: Path, tmp_path: Path) -> None:
    other = tmp_path / "other"
    spec(other, "101-x")
    add_project(vault, "other", "Other Name", other)
    spec(repo, "101-y")

    assert importer.main("Other Name") == 0

    assert step_file(vault, "101", "other").exists()
    assert not step_file(vault, "101", "demo").exists()


def test_unknown_project_exits_1(
    vault: Path, repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert importer.main("nope") == 1

    assert "no project 'nope'" in capsys.readouterr().err


def test_no_vault_says_run_init(vault: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert importer.main() == 1

    assert "hubd init" in capsys.readouterr().err


def test_missing_repo_and_broken_project_warn_and_keep_going(
    vault: Path, repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    add_project(vault, "a-gone", "Gone", tmp_path / "gone")
    broken = vault / "projects/b-broken"
    broken.mkdir()
    (broken / "project.md").write_text("---\nname: [\n---\n")
    spec(repo, "101-x")

    assert importer.main() == 0

    captured = capsys.readouterr()
    assert "warning: Gone" in captured.err and "b-broken" in captured.err
    assert "Demo: 1 new" in captured.out


def test_command_runs_from_the_cli(vault: Path, repo: Path) -> None:
    spec(repo, "101-x")

    result = subprocess.run(
        [sys.executable, "-m", "hubd", "import", "demo"],
        env=os.environ,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "Demo: 1 new, 0 kept" in result.stdout
