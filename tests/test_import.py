import hashlib
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


def test_model_from_a_command_whose_frontmatter_is_not_yaml(vault: Path, repo: Path) -> None:
    spec(repo, "101-first")
    spec(repo, "102-second")
    commands = repo / ".claude/commands"
    commands.mkdir(parents=True)
    (commands / "sprint-101.md").write_text("---\ndescription: A: b\nmodel: sonnet\n---\n")
    (commands / "sprint-102.md").write_text("---\ndescription: x\n---\nmodel: opus\n")

    assert importer.main() == 0

    assert _load_step(step_file(vault, "101")).model == "sonnet"
    assert _load_step(step_file(vault, "102")).model is None  # the prompt body does not count


def test_unreadable_command_file_warns_and_leaves_model_out(
    vault: Path, repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    spec(repo, "101-first")
    commands = repo / ".claude/commands"
    commands.mkdir(parents=True)
    (commands / "sprint-101.md").write_bytes(b"\xff\xfe")

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


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


def commit(repo: Path, name: str) -> None:
    (repo / name).write_text(name)
    git(repo, "add", name)
    git(repo, "commit", "-q", "-m", name)


def init_git(repo: Path, line: str = "main") -> None:
    git(repo, "init", "-q", "-b", line)
    git(repo, "config", "user.name", "test")
    git(repo, "config", "user.email", "test@hubd.invalid")
    commit(repo, "start")


def branch_with_work(repo: Path, branch: str, merge: bool, line: str = "main") -> None:
    git(repo, "checkout", "-q", "-b", branch)
    commit(repo, branch.replace("/", "_"))
    git(repo, "checkout", "-q", line)
    if merge:
        git(repo, "merge", "-q", "--no-ff", "-m", "merge", branch)


def progress(repo: Path, step_id: str, text: str, folder: str = "sprint/progress") -> None:
    path = repo / folder / f"{step_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def state(vault: Path, step_id: str) -> State:
    return _load_step(step_file(vault, step_id)).state


def test_progress_entry_with_merged_is_approved(vault: Path, repo: Path) -> None:
    spec(repo, "101-x")
    spec(repo, "102-y")
    (repo / "sprint/PROGRESS.md").write_text(
        "# Progress\n\n## 2026-10-30 — Step 101 Title (branch step/101-x)\nMerged and pushed.\n\n"
        "## 2026-10-29 — Step 102 Title (branch step/102-y)\nBuilt, 101 is not merged yet.\n"
    )

    importer.main()

    assert state(vault, "101") == State.approved
    assert state(vault, "102") == State.todo


def test_branch_merged_into_main_is_approved(vault: Path, repo: Path) -> None:
    init_git(repo)
    spec(repo, "101-x")
    spec(repo, "102-y")
    branch_with_work(repo, "step/101-x", merge=True)
    commit(repo, "later")
    branch_with_work(repo, "step/102-y", merge=False)

    importer.main()

    assert state(vault, "101") == State.approved
    assert state(vault, "102") == State.todo


def test_merged_check_uses_the_project_base(vault: Path, repo: Path, tmp_path: Path) -> None:
    """Like sprint-hub: `base: v2`; merged only into old `main` does not count."""
    origin = tmp_path / "origin"
    origin.mkdir()
    init_git(origin)
    git(origin, "checkout", "-q", "-b", "v2")
    commit(origin, "v2-start")
    clone = tmp_path / "clone"
    git(tmp_path, "clone", "-q", str(origin), str(clone))
    git(clone, "config", "user.name", "test")
    git(clone, "config", "user.email", "test@hubd.invalid")
    git(clone, "branch", "-q", "main", "origin/main")
    branch_with_work(clone, "step/101-x", merge=True, line="v2")
    commit(clone, "after-101")
    git(clone, "checkout", "-q", "main")
    branch_with_work(clone, "step/102-y", merge=True)
    git(clone, "checkout", "-q", "v2")
    add_project(vault, "clone", "Clone", clone)
    project = vault / "projects/clone/project.md"
    project.write_text(project.read_text().replace("model:", "base: v2\nmodel:"))
    spec(clone, "101-x")
    spec(clone, "102-y")

    importer.main()

    assert _load_step(step_file(vault, "101", "clone")).state == State.approved
    assert _load_step(step_file(vault, "102", "clone")).state == State.todo


def test_branch_still_at_the_tip_is_not_merged(vault: Path, repo: Path) -> None:
    init_git(repo)
    spec(repo, "101-x")
    git(repo, "branch", "step/101-x")

    importer.main()

    assert state(vault, "101") == State.todo


def test_all_ticked_is_done(vault: Path, repo: Path) -> None:
    spec(repo, "101-x")
    progress(repo, "101", "# Step 101\n- [x] one\n- [x] two\n")

    importer.main()

    assert state(vault, "101") == State.done


@pytest.mark.parametrize(
    "text", ["- [x] one\n- [~] two\n", "- [x] one\n- [ ] two\n", "# Step 101\n"]
)
def test_open_or_empty_checklist_is_todo(vault: Path, repo: Path, text: str) -> None:
    spec(repo, "101-x")
    progress(repo, "101", text)

    importer.main()

    assert state(vault, "101") == State.todo


def test_no_checklist_is_todo_never_doing(vault: Path, repo: Path) -> None:
    init_git(repo)
    spec(repo, "101-x")
    branch_with_work(repo, "step/101-x", merge=False)

    importer.main()

    assert state(vault, "101") == State.todo


def test_merged_beats_ticked(vault: Path, repo: Path) -> None:
    spec(repo, "101-x")
    progress(repo, "101", "- [x] one\n")
    (repo / "sprint/PROGRESS.md").write_text("## 2026-10-30 — Step 101 x\nMerged.\n")

    importer.main()

    assert state(vault, "101") == State.approved


@pytest.mark.parametrize("folder", ["sprint/archive/sprint-2/progress", "sprint/archive/progress"])
def test_archived_checklist_counts(vault: Path, repo: Path, folder: str) -> None:
    spec(repo, "201-x", "sprint/archive/sprint-2")
    progress(repo, "201", "- [x] one\n", folder)

    importer.main()

    assert state(vault, "201") == State.done


def test_branch_is_the_real_one_when_its_slug_differs(vault: Path, repo: Path) -> None:
    init_git(repo)
    spec(repo, "101-spec-slug")
    branch_with_work(repo, "step/101-real-slug", merge=False)

    importer.main()

    assert _load_step(step_file(vault, "101")).branch == "step/101-real-slug"


def test_repo_stays_byte_identical(vault: Path, repo: Path) -> None:
    init_git(repo)
    spec(repo, "101-x")
    spec(repo, "201-y", "sprint/archive/sprint-2")
    progress(repo, "101", "- [x] one\n")
    (repo / "sprint/PROGRESS.md").write_text("## 2026-10-30 — Step 201 y\nMerged.\n")
    branch_with_work(repo, "step/101-x", merge=True)
    before = snapshot(repo)

    importer.main()
    importer.main()

    assert snapshot(repo) == before


def test_sprint_from_the_readme_tables(vault: Path, repo: Path) -> None:
    (repo / "sprint/README.md").write_text(
        "## Sprints\n\n| Sprint | Track |\n|---|---|\n| 7 | work |\n\n"
        "## Sprint 9 — steps\n\n| # | File |\n|---|---|\n| a901 | `a901-x.md` |\n\n"
        "## Sprint 7 — planned (steps not written yet)\n\n| 702 | later |\n"
    )
    spec(repo, "a901-x")
    spec(repo, "702-y")

    importer.main()

    assert _load_step(step_file(vault, "a901")).sprint == 9
    assert _load_step(step_file(vault, "702")).sprint is None


def test_sprint_from_the_archive_readme(vault: Path, repo: Path) -> None:
    """BenWhispers: `archive/steps/` says nothing, only `archive/README.md` has the sprint."""
    spec(repo, "a401-x", "sprint/archive/steps")
    (repo / "sprint/archive/README.md").write_text("## Sprint 4 — steps\n\n| a401 | `x` |\n")

    importer.main()

    assert _load_step(step_file(vault, "a401")).sprint == 4


def test_sprint_from_the_archive_folder(vault: Path, repo: Path) -> None:
    spec(repo, "b12-x", "sprint/archive/sprint-3")

    importer.main()

    assert _load_step(step_file(vault, "b12")).sprint == 3


def test_no_sprint_is_left_out_and_listed(
    vault: Path, repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    spec(repo, "a901-x")
    spec(repo, "101-y")

    importer.main()

    assert "Demo: 2 new, 0 kept, 2 no sprint (101, a901)" in capsys.readouterr().out
    assert "sprint:" not in step_file(vault, "a901").read_text()


def test_sprint_folder_in_the_repo_path_is_not_a_sprint(vault: Path, tmp_path: Path) -> None:
    """`archive/steps/` under a repo called `sprint-2` or `sprint-hub` has no sprint."""
    for name in ("sprint-2", "sprint-hub"):
        repo = tmp_path / name
        spec(repo, "a401-x", "sprint/archive/steps")
        add_project(vault, name, name, repo)

    assert importer.main() == 0

    for name in ("sprint-2", "sprint-hub"):
        assert _load_step(step_file(vault, "a401", name)).sprint is None
    assert load_vault(vault).errors == []


def snapshot(path: Path) -> dict[str, str]:
    return {
        str(p.relative_to(path)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(path.rglob("*"))
        if p.is_file()
    }


def test_only_imports_the_named_spec(vault: Path, repo: Path) -> None:
    spec(repo, "101-first")
    second = spec(repo, "102-second")
    folder = vault / "projects" / "demo"
    project = load_vault(vault).projects["demo"]

    importer.import_project(folder, project, repo, only=second)

    assert not step_file(vault, "101").exists()
    assert step_file(vault, "102").is_file()
