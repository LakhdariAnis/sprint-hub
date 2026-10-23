import re
from pathlib import Path

from hubd.theme import VARS, FakeTheme, OmarchyTheme, read

FIXTURE = Path(__file__).parent / "fixtures" / "theme" / "colors.toml"
THEME_CSS = Path(__file__).parents[1] / "web" / "src" / "theme.css"


def test_real_colors_toml_maps_every_var() -> None:
    # Contract: a copy of a real Omarchy colors.toml (Aether, Omarchy v4).
    theme, warnings = read(OmarchyTheme(FIXTURE))
    assert warnings == []
    assert theme["mode"] == "dark"
    assert set(theme["vars"]) == set(VARS.values())
    assert theme["vars"]["--bg"] == "#020800"
    assert theme["vars"]["--fg2"] == "#f3f2ef"


def test_fake_theme_matches_theme_css_defaults() -> None:
    css = dict(re.findall(r"^\s*(--\w+): (#[0-9a-f]{6});", THEME_CSS.read_text(), re.M))
    theme, warnings = read(FakeTheme())
    assert warnings == []
    assert theme["vars"] == css


def test_missing_file(tmp_path: Path) -> None:
    theme, warnings = read(OmarchyTheme(tmp_path / "colors.toml"))
    assert theme == {"vars": {}, "mode": "dark"}
    assert warnings == ["theme file not found: default colours"]


def test_bad_toml(tmp_path: Path) -> None:
    path = tmp_path / "colors.toml"
    path.write_text("background = \n")
    theme, warnings = read(OmarchyTheme(path))
    assert theme["vars"] == {}
    assert warnings[0].startswith("cannot read theme: ")


def test_missing_key_and_bad_value_keep_defaults(tmp_path: Path) -> None:
    path = tmp_path / "colors.toml"
    lines = [line for line in FIXTURE.read_text().splitlines() if not line.startswith("red ")]
    text = "\n".join(lines).replace('accent = "#4c7dff"', 'accent = "blue"')
    path.write_text(text.replace('mode = "dark"', 'mode = "light"'))
    theme, warnings = read(OmarchyTheme(path))
    assert "--r" not in theme["vars"] and "--ac" not in theme["vars"]
    assert len(theme["vars"]) == len(VARS) - 2
    assert theme["mode"] == "light"
    assert warnings == [
        "theme accent = 'blue' is not #rrggbb: --ac keeps its default",
        "theme has no red: --r keeps its default",
    ]
