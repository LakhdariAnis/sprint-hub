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
    """(name, absolute repo path) of every project in `config`; ValueError if it is not usable."""
    try:
        data = tomllib.loads(config.read_text())
    except OSError as exc:
        raise ValueError(f"cannot read {config}: {exc.strerror}") from None
    except ValueError as exc:  # bad TOML or bad UTF-8
        raise ValueError(f"{config}: {exc}") from None
    entries = data.get("project")
    if not entries or not isinstance(entries, list):
        raise ValueError(f"{config}: no [[project]] entries")
    projects: list[tuple[str, Path]] = []
    folders: set[str] = set()
    for p in entries:
        if not isinstance(p, dict) or not all(isinstance(p.get(k), str) for k in ("name", "path")):
            raise ValueError(f"{config}: every [[project]] needs a name and a path")
        name = p["name"]
        # The slug is a folder name under projects/: it must stay there.
        if slug(name) in ("", ".", "..") or "/" in name:
            raise ValueError(f"{config}: bad project name {name!r}")
        if slug(name) in folders:
            raise ValueError(f"{config}: two projects share the folder {slug(name)!r}")
        folders.add(slug(name))
        projects.append((name, Path(os.path.abspath(os.path.expanduser(p["path"])))))
    return projects


def create(folder: Path, name: str, repo: Path) -> None:
    (folder / "steps").mkdir(parents=True, exist_ok=True)
    meta = {"name": name, "repo": str(repo), "model": "sonnet", "merge": "manual"}
    text = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True)
    # "x": a project.md is never overwritten, whatever happened since the exists() check.
    with (folder / "project.md").open("x") as f:
        f.write(f"---\n{text}---\n")


def main(config: Path = PROJECTS) -> int:
    try:
        projects = load_projects(config)
    except ValueError as exc:
        print(f"hubd init: {exc}", file=sys.stderr)
        return 1
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
