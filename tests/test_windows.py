import asyncio
from pathlib import Path

import pytest

from hubd import windows

LINE = "openwindow>>61c8f1a3ed50,4,foot,hubtest"


def environ(tmp_path: Path, pid: int, *items: bytes) -> None:
    (tmp_path / str(pid)).mkdir()
    (tmp_path / str(pid) / "environ").write_bytes(b"\0".join(items) + b"\0")


def test_opened_reads_only_openwindow() -> None:
    assert windows.opened(LINE) == ("0x61c8f1a3ed50", "4")
    assert windows.opened("openwindow>>61c8,9,a,b, with, commas") == ("0x61c8", "9")
    assert windows.opened("activewindowv2>>61c8f14e3300") is None
    assert windows.opened("openwindow>>broken") is None


def test_workspace_of_takes_digits_only(tmp_path: Path) -> None:
    environ(tmp_path, 10, b"PATH=/bin", b"HUB_WORKSPACE=3")
    environ(tmp_path, 11, b'HUB_WORKSPACE=3" })')  # never into the Lua string
    environ(tmp_path, 12, b"MY_HUB_WORKSPACE=3")
    assert windows.workspace_of(10, tmp_path) == "3"
    assert windows.workspace_of(11, tmp_path) is None
    assert windows.workspace_of(12, tmp_path) is None
    assert windows.workspace_of(99, tmp_path) is None  # gone


def test_place_moves_only_a_window_off_its_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(windows, "_pid", lambda address, env: 10)
    environ(tmp_path, 10, b"HUB_WORKSPACE=3")
    assert windows.place(LINE, {}, tmp_path) == [
        "hyprctl",
        "dispatch",
        'hl.dsp.window.move({ workspace = "3", follow = false, '
        'window = "address:0x61c8f1a3ed50" })',
    ]
    assert windows.place(LINE.replace(",4,", ",3,"), {}, tmp_path) is None  # there already
    monkeypatch.setattr(windows, "_pid", lambda address, env: 11)
    assert windows.place(LINE, {}, tmp_path) is None  # not started by hubd


def test_loop_without_hyprland_ends_on_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(windows.session, "env", lambda: {})

    async def run() -> None:
        stop = asyncio.Event()
        task = asyncio.create_task(windows.loop(stop))
        await asyncio.sleep(0.05)
        stop.set()
        await asyncio.wait_for(task, 1)

    asyncio.run(run())


def test_follow_moves_each_opened_window_and_ends_on_stop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    moved: list[str] = []
    monkeypatch.setattr(windows, "_move", lambda line, env: moved.append(line))

    async def run() -> None:
        reader, stop = asyncio.StreamReader(), asyncio.Event()
        reader.feed_data(f"{LINE}\nactivewindowv2>>61c8\n".encode())
        task = asyncio.create_task(windows._follow(reader, {}, stop))
        await asyncio.sleep(0.05)
        stop.set()
        await asyncio.wait_for(task, 1)

    asyncio.run(run())
    assert moved == [LINE, "activewindowv2>>61c8"]
