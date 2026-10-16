"""Load the vault into an in-memory index (docs/HUB-DESIGN.md section 4)."""

import re

from hubd.model import Review, Run

_HEADING = re.compile(r"^## (.+?)\s*$")
# ` # ...` after a value is a YAML-style comment, e.g. `verdict: changes  # approve | changes`.
# shortcut: a ` #` inside a review comment is cut too, use a real escape if that ever bites.
_COMMENT = re.compile(r"\s+#.*$")
_SIZE = {"k": 1_000, "M": 1_000_000}


def split_sections(body: str) -> dict[str, list[str]]:
    """`## Name` heading -> the lines under it, up to the next `## ` heading."""
    sections: dict[str, list[str]] = {}
    lines: list[str] | None = None
    for line in body.splitlines():
        if m := _HEADING.match(line):
            lines = sections.setdefault(m[1], [])
        elif lines is not None:
            lines.append(line)
    return sections


def parse_run(line: str) -> Run:
    """`- 2026-10-15 22:10 · sonnet · session 7b1e…a04 · 42 min · 1.2M tokens · task all`."""
    started, model, *rest = (part.strip() for part in line.removeprefix("- ").split("·"))
    fields: dict[str, object] = {"started": started, "model": model}
    for part in rest:
        key, _, value = part.partition(" ")
        if key in ("session", "task"):
            fields[key] = value
        elif value == "min":
            fields["minutes"] = key
        elif value == "tokens":
            num, unit = (key[:-1], key[-1]) if key[-1] in _SIZE else (key, "")
            fields["tokens"] = round(float(num) * _SIZE.get(unit, 1))
        else:
            raise ValueError(f"unknown run field {part!r}")
    return Run.model_validate(fields)


def parse_review(lines: list[str]) -> Review:
    """`key: value` lines; an empty value means not set."""
    fields = {}
    for line in lines:
        key, sep, value = _COMMENT.sub("", line).partition(":")
        if sep and (value := value.strip()):
            fields[key.strip()] = value
    return Review.model_validate(fields)


def parse_body(body: str) -> tuple[list[Run], Review | None]:
    sections = split_sections(body)
    runs = [parse_run(line) for line in sections.get("Runs", []) if line.startswith("- ")]
    review = parse_review(sections["Review"]) if "Review" in sections else None
    return runs, review
