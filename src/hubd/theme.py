"""App colours from the desktop theme behind one interface (docs/ROADMAP.md rule 4)."""

import asyncio
import re
import tomllib
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from watchfiles import awatch

OMARCHY = Path.home() / ".local/state/omarchy/current/theme/colors.toml"

# colors.toml key → CSS var in web/src/theme.css.
VARS = {
    "background": "--bg",
    "dark_background": "--dk",
    "darker_background": "--dkr",
    "lighter_background": "--lt",
    "selection": "--sel",
    "muted": "--mu",
    "foreground": "--fg",
    "light_foreground": "--fg2",
    "dark_foreground": "--fg3",
    "accent": "--ac",
    "red": "--r",
    "yellow": "--y",
    "orange": "--o",
    "green": "--g",
    "cyan": "--c",
    "blue": "--b",
    "magenta": "--m",
}
HEX = re.compile(r"#[0-9a-fA-F]{6}")


class ThemeSource(Protocol):
    path: Path  # shown in /errors next to a warning

    def colors(self) -> dict[str, str]:
        """Keys as colors.toml names them. Raises OSError or ValueError when unreadable."""
        ...


class OmarchyTheme:
    def __init__(self, path: Path = OMARCHY):
        self.path = path

    def colors(self) -> dict[str, str]:
        with self.path.open("rb") as f:
            return tomllib.load(f)


class FakeTheme:
    """Everforest, the defaults in web/src/theme.css."""

    path = Path("fake-theme")

    def colors(self) -> dict[str, str]:
        return {
            "mode": "dark",
            "background": "#2d353b",
            "dark_background": "#21272c",
            "darker_background": "#181d20",
            "lighter_background": "#343f44",
            "selection": "#3d484d",
            "muted": "#475258",
            "foreground": "#d3c6aa",
            "light_foreground": "#9da9a0",
            "dark_foreground": "#4f585e",
            "accent": "#7fbbb3",
            "red": "#e67e80",
            "yellow": "#dbbc7f",
            "orange": "#e09d7f",
            "green": "#a7c080",
            "cyan": "#83c092",
            "blue": "#7fbbb3",
            "magenta": "#d699b6",
        }


def read(source: ThemeSource) -> tuple[dict, list[str]]:
    """`({vars, mode}, warnings)`. Fails soft: a var left out keeps its theme.css default."""
    try:
        colors = source.colors()
    except FileNotFoundError:
        return {"vars": {}, "mode": "dark"}, ["theme file not found: default colours"]
    except (OSError, ValueError) as exc:  # tomllib.TOMLDecodeError is a ValueError
        return {"vars": {}, "mode": "dark"}, [f"cannot read theme: {exc}"]
    css, warnings = {}, []
    for name, var in VARS.items():
        value = colors.get(name)
        if value is None:
            warnings.append(f"theme has no {name}: {var} keeps its default")
        elif isinstance(value, str) and HEX.fullmatch(value):
            css[var] = value
        else:
            warnings.append(f"theme {name} = {value!r} is not #rrggbb: {var} keeps its default")
    mode = colors.get("mode")
    return {"vars": css, "mode": mode if mode in ("dark", "light") else "dark"}, warnings


async def watch(source: OmarchyTheme, emit: Callable[[dict], None], stop: asyncio.Event) -> None:
    """Emit a `theme` event when the colours change, until `stop`."""
    # omarchy-theme-set does `rm -rf current/theme; mv next-theme current/theme`: the file is
    # replaced, not edited, so watch its grandparent folder and re-read on any change under it.
    root = source.path.parent.parent
    if not root.is_dir():
        return  # shortcut: no Omarchy at start means no watching; restart hubd after installing it
    last = read(source)[0]

    def relevant(_: object, path: str) -> bool:
        return Path(path).name in ("theme", "theme.name", "colors.toml")

    async for _ in awatch(root, watch_filter=relevant, debounce=100, stop_event=stop):
        now = read(source)[0]
        if now != last:  # a switch fires several file events; one theme event
            last = now
            emit({"type": "theme", **now})
