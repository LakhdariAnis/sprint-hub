"""`hubd init`: create the vault, one project per `projects.toml` entry. Safe to run again."""

import os
import sys
import tomllib
from pathlib import Path

import yaml

from hubd.daemon import vault_path

PROJECTS = Path("~/.config/sprint-hub/projects.toml").expanduser()


def slug(name: str) -> str:
    return name.lower().replace(" ", "-")


def load_projects(config: Path) -> list[tuple[str, Path]]:
    """(name, absolute repo path) of every project in `config`."""
    data = tomllib.loads(config.read_text())
    return [
        (p["name"], Path(os.path.abspath(os.path.expanduser(p["path"])))) for p in data["project"]
    ]


def create(folder: Path, name: str, repo: Path) -> None:
    (folder / "steps").mkdir(parents=True, exist_ok=True)
    meta = {"name": name, "repo": str(repo), "model": "sonnet", "merge": "manual"}
    text = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True)
    # "x": a project.md is never overwritten, whatever happened since the exists() check.
    with (folder / "project.md").open("x") as f:
        f.write(f"---\n{text}---\n")


def main(config: Path = PROJECTS) -> int:
    projects = load_projects(config)
    vault = vault_path()
    try:
        (vault / "projects").mkdir(parents=True, exist_ok=True)
        for name, repo in projects:
            folder = vault / "projects" / slug(name)
            if (folder / "project.md").exists():
                print(f"{name}: already exists")
            elif not repo.is_dir():
                print(f"warning: {name}: {repo} does not exist, skipped", file=sys.stderr)
            else:
                create(folder, name, repo)
                print(f"{name}: created {folder}")
    except OSError as exc:
        print(f"hubd init: {exc}", file=sys.stderr)
        return 1
    return 0
