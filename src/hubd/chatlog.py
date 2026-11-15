"""The chats Anis started, kept in the vault: `projects/<project>/chats.md`, `chats/scratch.md`.

Only what hubd needs to list a chat and resume it. The turns stay in Claude's session file.
"""

import logging
import re
from dataclasses import dataclass, fields, replace
from datetime import datetime
from pathlib import Path

from hubd.model import one_line
from hubd.vault import _write_atomic

log = logging.getLogger(__name__)

TITLE = 40  # characters of the first message that name a chat
HEAD = "# Chats\n"
_KEY = re.compile(r"^- (\w+): ?(.*)$")


@dataclass
class ChatEntry:
    id: str  # Claude's session id
    title: str
    model: str
    effort: str
    kind: str  # what Claude was told: none, project, sprint or step
    created: datetime
    used: datetime
    sprint: int | None = None
    step: str | None = None
    open: bool = True  # in the sidebar; `x` sets it off, the entry stays


def title_of(text: str) -> str:
    text = one_line(text)
    return text if len(text) <= TITLE else text[: TITLE - 1].rstrip() + "…"


def path_of(vault: Path, project: str | None) -> Path:
    return vault / "projects" / project / "chats.md" if project else vault / "chats" / "scratch.md"


def _format(e: ChatEntry) -> str:
    lines = [f"## {e.id}"]
    for f in fields(e):
        value = getattr(e, f.name)
        if f.name == "id" or value is None:
            continue
        if isinstance(value, datetime):
            value = value.isoformat(timespec="seconds")
        lines.append(f"- {f.name}: {'yes' if value is True else 'no' if value is False else value}")
    return "\n".join(lines)


def _parse(id: str, block: list[str]) -> ChatEntry:
    given = {m[1]: m[2].strip() for line in block if (m := _KEY.match(line))}
    return ChatEntry(
        id=id,
        title=given["title"],
        model=given["model"],
        effort=given["effort"],
        kind=given.get("kind", "none"),
        created=datetime.fromisoformat(given["created"]),
        used=datetime.fromisoformat(given["used"]),
        sprint=int(given["sprint"]) if "sprint" in given else None,
        step=given.get("step"),
        open=given.get("open", "yes") != "no",
    )


def load(path: Path) -> list[ChatEntry]:
    """Every entry of the file. A missing file is no chats; a bad entry is skipped."""
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return []
    blocks: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in lines:
        if line.startswith("## "):
            current = blocks.setdefault(line[3:].strip(), [])
        elif current is not None:
            current.append(line)
    entries = []
    for id, block in blocks.items():
        try:
            entries.append(_parse(id, block))
        except (KeyError, ValueError) as exc:
            log.warning("chats: skipped entry %s in %s (%r)", id, path, exc)
    return entries


def save(path: Path, entry: ChatEntry) -> None:
    """Add the entry, or replace the one with its id. The other entries stay as they are."""
    entries = load(path)
    entries = [entry if e.id == entry.id else e for e in entries]
    if entry.id not in [e.id for e in entries]:
        entries.append(entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_atomic(path, (HEAD + "".join("\n" + _format(e) + "\n" for e in entries)).encode())


def change(path: Path, chat_id: str, **changes: object) -> ChatEntry | None:
    """New values for the fields of one entry (rename, close, touch). None: no such chat."""
    entry = next((e for e in load(path) if e.id == chat_id), None)
    if entry is None:
        return None
    entry = replace(entry, **changes)
    save(path, entry)
    return entry
