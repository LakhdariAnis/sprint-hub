import re
from pathlib import Path

from fastapi.testclient import TestClient

from hubd.api import create_app
from hubd.daemon import Hub
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


def test_get_theme_defaults_to_fake() -> None:
    body = TestClient(create_app()).get("/theme").json()
    assert body == {"vars": read(FakeTheme())[0]["vars"], "mode": "dark"}


def test_get_theme_omarchy() -> None:
    body = TestClient(create_app(theme=OmarchyTheme(FIXTURE))).get("/theme").json()
    assert body["vars"]["--ac"] == "#4c7dff"


def test_theme_warnings_in_errors(hub: Hub, tmp_path: Path) -> None:
    missing = tmp_path / "colors.toml"
    errors = TestClient(create_app(hub, theme=OmarchyTheme(missing))).get("/errors").json()
    assert errors[-1] == {
        "path": str(missing),
        "line": None,
        "message": "theme file not found: default colours",
    }


def test_theme_swap_emits_one_theme_event(tmp_path: Path) -> None:
    import asyncio
    import shutil

    from hubd.theme import watch

    current = tmp_path / "current"
    (current / "theme").mkdir(parents=True)
    shutil.copy(FIXTURE, current / "theme" / "colors.toml")
    source = OmarchyTheme(current / "theme" / "colors.toml")

    async def swap() -> list[dict]:
        events: list[dict] = []
        stop = asyncio.Event()
        task = asyncio.create_task(watch(source, events.append, stop))
        await asyncio.sleep(0.3)  # let the watcher start
        # What omarchy-theme-set does: stage a new folder, delete the old, move it in.
        (current / "next-theme").mkdir()
        text = FIXTURE.read_text().replace('"#020800"', '"#fafafa"')
        text = text.replace('mode = "dark"', 'mode = "light"')
        (current / "next-theme" / "colors.toml").write_text(text)
        shutil.rmtree(current / "theme")
        (current / "next-theme").rename(current / "theme")
        (current / "theme.name").write_text("paper")
        await asyncio.sleep(0.8)
        stop.set()
        await task
        return events

    events = asyncio.run(swap())
    assert len(events) == 1
    assert events[0]["type"] == "theme"
    assert events[0]["mode"] == "light"
    assert events[0]["vars"]["--bg"] == "#fafafa"
