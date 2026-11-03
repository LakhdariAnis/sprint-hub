"""Run the theme mapping over every installed Omarchy theme and list the ones that fail.

    uv run python scripts/theme-sweep.py

Fails (exit 1) when a theme has no colors.toml, cannot be read, leaves a var unmapped, or still
reads under MIN_CONTRAST after the mapping. Prints one line per theme.
"""

import sys
from pathlib import Path

from hubd.theme import MIN_CONTRAST, STATES, TEXT, VARS, OmarchyTheme, contrast, ratios, read

FOLDERS = [
    Path.home() / ".config/omarchy/themes",
    Path.home() / ".local/share/omarchy/themes",
    Path("/usr/share/omarchy/themes"),
]


def problems(colors: Path) -> list[str]:
    if not colors.is_file():
        return ["no colors.toml"]
    theme, warnings = read(OmarchyTheme(colors))
    css = theme["vars"]
    if len(css) < len(VARS):
        return warnings
    found = list(warnings)
    if (low := contrast(css["--fg"], css["--bg"])) < MIN_CONTRAST:
        found.append(f"--fg on --bg {low:.2f}:1")
    for var in (*TEXT, *STATES):
        found += [f"{var} on {on} {r:.2f}:1" for on, r in ratios(css, var) if r < MIN_CONTRAST]
    return found


def main() -> int:
    failed = 0
    for folder in FOLDERS:
        for theme in sorted(p for p in folder.glob("*") if p.is_dir()):
            found = problems(theme / "colors.toml")
            failed += bool(found)
            print(f"{'FAIL' if found else 'ok  '} {theme.name}: {'; '.join(found)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
