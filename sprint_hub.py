#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["textual"]
# ///
"""sprint-hub: browse sprint steps of your projects and start them."""
import re
import subprocess
import tomllib
from pathlib import Path

from rich.markup import escape
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.theme import Theme
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Label,
    ListItem,
    ListView,
    ProgressBar,
    Static,
)

CONFIG = Path("~/.config/sprint-hub/projects.toml").expanduser()
THEME_FILE = Path("~/.local/state/omarchy/current/theme/colors.toml").expanduser()
DEFAULT_CONFIG = '[[project]]\nname = "BenWhispers"\npath = "~/Work/benwhispers/benwhispers_app"\n'
STATUS_LABEL = {"done": "✔ done", "doing": "● in progress", "todo": "○ todo"}


# ---------- data ----------

def load_projects() -> list[dict]:
    if not CONFIG.exists():
        CONFIG.parent.mkdir(parents=True, exist_ok=True)
        CONFIG.write_text(DEFAULT_CONFIG)
    data = tomllib.loads(CONFIG.read_text())
    return [
        {"name": p["name"], "path": Path(p["path"]).expanduser()}
        for p in data.get("project", [])
    ]


def frontmatter(text: str) -> dict:
    m = re.match(r"---\n(.*?)\n---", text, re.S)
    out = {}
    for line in (m.group(1) if m else "").splitlines():
        k, _, v = line.partition(":")
        out[k.strip()] = v.strip()
    return out


def git(path: Path, *args: str) -> list[str]:
    r = subprocess.run(["git", "-C", str(path), *args], capture_output=True, text=True)
    return r.stdout.split() if r.returncode == 0 else []


def progress_merged(path: Path) -> set[str]:
    """Step ids whose PROGRESS.md entry ('## date — Step NN ...') says it was merged."""
    f = path / "sprint" / "PROGRESS.md"
    if not f.exists():
        return set()
    done = set()
    for block in re.split(r"(?m)^## ", f.read_text())[1:]:
        m = re.match(r".*?Step (\w+)", block.splitlines()[0])
        if m and re.search(r"[Mm]erged", block):
            done.add(m.group(1).lower())
    return done


def checklist(path: Path, sid: str) -> tuple[list[tuple[str, str]], int, int]:
    """Lines of sprint/progress/<sid>.md as (mark, text), plus (ticked, total)."""
    f = path / "sprint" / "progress" / f"{sid}.md"
    if not f.exists():
        return [], 0, 0
    items = re.findall(r"(?m)^\s*[-*] \[([ xX~])\] (.+)$", f.read_text())
    items = [(m.lower(), txt.strip()) for m, txt in items]
    return items, sum(m == "x" for m, _ in items), len(items)


def status_label(s: dict) -> str:
    label = STATUS_LABEL[s["status"]]
    return f"{label}  {s['ticked']}/{s['total']}" if s["total"] and s["status"] != "done" else label


def load_steps(path: Path) -> list[dict]:
    main = "main" if git(path, "rev-parse", "--verify", "main") else "master"
    main_tip = git(path, "rev-parse", main)
    merged = {b.lstrip("*+") for b in git(path, "branch", "--merged", main)}
    branches = [b.lstrip("*+") for b in git(path, "branch", "--format=%(refname:short)")]
    logged = progress_merged(path)
    steps = []
    for f in sorted((path / ".claude" / "commands").glob("sprint-*.md")):
        sid = f.stem.removeprefix("sprint-")
        fm = frontmatter(f.read_text())
        mine = [b for b in branches if b.startswith(f"step/{sid}-")]
        if sid.lower() in logged or any(
            b in merged and git(path, "rev-parse", b) != main_tip for b in mine
        ):
            status = "done"
        elif mine or (path / "sprint" / "progress" / f"{sid}.md").exists():
            status = "doing"
        else:
            status = "todo"
        spec = next(iter((path / "sprint").glob(f"{sid}-*.md")), None)
        _, ticked, total = checklist(path, sid)
        steps.append({
            "id": sid,
            "title": fm.get("description", "").removeprefix(f"Sprint {sid} - "),
            "model": fm.get("model", "?"),
            "status": status,
            "spec": spec,
            "ticked": ticked,
            "total": total,
        })
    return steps


def omarchy_theme() -> Theme | None:
    try:
        c = tomllib.loads(THEME_FILE.read_text())
        return Theme(
            name="omarchy",
            primary=c["accent"],
            secondary=c["blue"],
            accent=c["accent"],
            warning=c["yellow"],
            error=c["red"],
            success=c["green"],
            foreground=c["foreground"],
            background=c["background"],
            surface=c["lighter_background"],
            panel=c["dark_background"],
            dark=c.get("mode", "dark") == "dark",
        )
    except (OSError, KeyError, tomllib.TOMLDecodeError):
        return None


# ---------- screens ----------

class ProjectsScreen(Screen):
    BINDINGS = [Binding("r", "refresh", "Refresh")]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("Projects", classes="title")
        yield ListView(id="projects")
        yield Footer()

    def on_mount(self) -> None:
        self.action_refresh()

    def action_refresh(self) -> None:
        self.projects = load_projects()
        lv = self.query_one(ListView)
        lv.clear()
        for p in self.projects:
            lv.append(ListItem(Label(f"{p['name']}   [dim]{p['path']}[/dim]")))
        if self.projects:
            lv.index = 0
        lv.focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        self.app.push_screen(StepsScreen(self.projects[event.list_view.index]))


class StepsScreen(Screen):
    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back"),
        Binding("r", "refresh", "Refresh"),
        Binding("enter", "start", "Start"),
    ]

    def __init__(self, project: dict) -> None:
        super().__init__()
        self.project = project
        self.steps: list[dict] = []

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label(self.project["name"], classes="title")
        yield ProgressBar(total=1, show_eta=False, id="bar")
        with Horizontal():
            yield DataTable(id="steps", cursor_type="row")
            with Vertical(id="side"):
                yield Static("Select a step.", id="desc")
                yield Button("Start", id="start", variant="primary")
        yield Footer()

    def on_mount(self) -> None:
        t = self.query_one(DataTable)
        for col in ("id", "title", "model", "status"):
            t.add_column(col, key=col)
        self.action_refresh()
        t.focus()
        self.set_interval(2, self.tick)

    def tick(self) -> None:
        """Live-update the checklist of every step while Claude ticks it."""
        t = self.query_one(DataTable)
        for s in self.steps:
            _, ticked, total = checklist(self.project["path"], s["id"])
            if (ticked, total) != (s["ticked"], s["total"]):
                s["ticked"], s["total"] = ticked, total
                if s["status"] == "todo" and total:
                    s["status"] = "doing"
                t.update_cell(s["id"], "status", status_label(s))
        if s := self.current():
            self.show_step(s)

    def action_refresh(self) -> None:
        t = self.query_one(DataTable)
        row = t.cursor_row
        t.clear()
        self.steps = load_steps(self.project["path"])
        for s in self.steps:
            t.add_row(s["id"], s["title"], s["model"], status_label(s), key=s["id"])
        done = sum(s["status"] == "done" for s in self.steps)
        bar = self.query_one(ProgressBar)
        bar.update(total=max(len(self.steps), 1), progress=done)
        self.query_one(".title", Label).update(
            f"{self.project['name']}   {done}/{len(self.steps)} done"
        )
        if self.steps:
            t.move_cursor(row=min(row, len(self.steps) - 1))
            self.show_step(self.steps[t.cursor_row])

    def show_step(self, s: dict) -> None:
        items, ticked, total = checklist(self.project["path"], s["id"])
        icon = {"x": "[green]✔[/green]", "~": "[yellow]●[/yellow]", " ": "[dim]○[/dim]"}
        head = ""
        if items:
            lines = [f"{icon[m]} {escape(txt)}" for m, txt in items]
            head = (
                f"[b]Checklist {ticked}/{total}[/b]\n"
                + "\n".join(lines)
                + "\n\n[dim]── spec ──[/dim]\n"
            )
        text = s["spec"].read_text() if s["spec"] else "(no spec file in sprint/)"
        body = head + escape("\n".join(text.splitlines()[:25]))
        if body != getattr(self, "_desc", None):
            self._desc = body
            self.query_one("#desc", Static).update(body)

    def current(self) -> dict | None:
        i = self.query_one(DataTable).cursor_row
        return self.steps[i] if 0 <= i < len(self.steps) else None

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if self.steps and event.cursor_row < len(self.steps):
            self.show_step(self.steps[event.cursor_row])

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self.action_start()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.action_start()

    def action_start(self) -> None:
        s = self.current()
        if not s:
            return
        subprocess.Popen(
            ["setsid", "xdg-terminal-exec", f"--dir={self.project['path']}", "bw", s["id"]],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
        )
        self.app.notify(f"Started bw {s['id']}")


class SprintHub(App):
    CSS = """
    .title { padding: 1 2; text-style: bold; color: $accent; }
    #projects { margin: 0 2; }
    #bar { padding: 0 2; }
    #steps { width: 3fr; }
    #side { width: 2fr; padding: 0 1; border-left: tall $primary; }
    #desc { height: 1fr; overflow-y: auto; }
    """
    BINDINGS = [Binding("q", "quit", "Quit")]
    TITLE = "sprint-hub"

    def on_mount(self) -> None:
        theme = omarchy_theme()
        if theme:
            self.register_theme(theme)
            self.theme = "omarchy"
        else:
            self.theme = "textual-dark"
        self.push_screen(ProjectsScreen())


if __name__ == "__main__":
    SprintHub().run()
