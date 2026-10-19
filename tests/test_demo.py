import subprocess

from hubd.demo import demo_vault


def test_demo_vault_is_a_git_repo_without_broken() -> None:
    vault = demo_vault()
    assert not (vault / "projects" / "broken").exists()
    out = subprocess.run(
        ["git", "log", "--format=%D"], cwd=vault / "demo-repo", capture_output=True, text=True
    )
    assert "main" in out.stdout
