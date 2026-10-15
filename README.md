# sprint-hub

Terminal UI (Python + Textual) to browse sprint steps of your projects and start them.

## Install
Needs `uv` (dependencies are fetched automatically, no sudo). Alternative: `sudo pacman -S python-textual`.

    ln -s ~/Work/sprint-hub/sprint_hub.py ~/.local/bin/sprint-hub   # or use the launcher script already there
    sprint-hub

First run creates `~/.config/sprint-hub/projects.toml`:

    [[project]]
    name = "BenWhispers"
    path = "~/Work/benwhispers/benwhispers_app"

## Keys
Click/Enter open a project or start a step · `q` quit · `r` refresh · `Esc` back.

## Hyprland
`Super+Shift+S` in `~/.config/hypr/bindings.lua`:

    hl.unbind("SUPER + SHIFT + S")
    o.bind("SUPER + SHIFT + S", "Sprint Hub", "omarchy-launch-terminal sprint-hub")

See `RULES.md` for the expected project format.
