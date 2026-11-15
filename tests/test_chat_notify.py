"""Popups of a chat that answers or asks (612b), with FakeChat."""

import pytest
from conftest import Recorder
from fastapi.testclient import TestClient
from test_api_chats import NEW, asked, client, until

from hubd import focus
from hubd.daemon import WAIT_GAP, Hub


def ended(events: list[dict], n: int = 1) -> None:
    until(lambda: [e["kind"] for e in events].count("turn_end") == n)


def say(c: TestClient, text: str) -> str:
    chat_id = c.post("/chats", json=NEW).json()["id"]
    c.post(f"/chats/{chat_id}/message", json={"text": text})
    return chat_id


def test_turn_end_notifies(hub: Hub, notifier: Recorder) -> None:
    c, events = client(hub)
    with c:
        say(c, "say hi")
        ended(events)
    assert notifier.sent == [("Claude answered", "say hi")]


def test_permission_notifies_with_the_file_or_the_command(hub: Hub, notifier: Recorder) -> None:
    c, events = client(hub)
    with c:
        asked(c, events, "run ls")
        asked(c, events, "run " + "x" * 60)
    assert notifier.sent == [
        ("Claude needs permission", "Bash: ls"),
        ("Claude needs permission", "Bash: " + "x" * 40),
    ]


def test_permission_timeout_notifies(hub: Hub, notifier: Recorder) -> None:
    c, events = client(hub)
    with c:
        c.app.state.chats.ask_wait = 0.05  # "0 min": the text takes the minutes from ask_wait
        asked(c, events, "run ls")
        ended(events)
    assert [t for t, _ in notifier.sent] == [
        "Claude needs permission",
        "Permission denied after 0 min",
        "Claude answered",
    ]
    assert notifier.sent[1][1] == "run ls"


def test_one_popup_per_chat_and_kind_every_30_s(hub: Hub, notifier: Recorder) -> None:
    c, events = client(hub)
    with c:
        chat_id = say(c, "one")
        ended(events)
        c.post(f"/chats/{chat_id}/message", json={"text": "two"})
        ended(events, 2)
        assert len(notifier.sent) == 1
        later = hub.clock() + WAIT_GAP
        hub.clock = lambda: later
        c.post(f"/chats/{chat_id}/message", json={"text": "three"})
        ended(events, 3)
    assert len(notifier.sent) == 2


def present(c: TestClient, window: str, focused: bool, chat: str | None) -> None:
    body = {"window": window, "focused": focused, "chat": chat}
    assert c.post("/presence", json=body).status_code == 200


def test_focused_window_on_the_chat_keeps_it_quiet(hub: Hub, notifier: Recorder) -> None:
    c, events = client(hub)
    with c:
        chat_id = c.post("/chats", json=NEW).json()["id"]
        present(c, "w1", True, chat_id)
        c.post(f"/chats/{chat_id}/message", json={"text": "say hi"})
        ended(events)
    assert notifier.sent == []


def test_focused_window_on_another_chat_still_notifies(hub: Hub, notifier: Recorder) -> None:
    c, events = client(hub)
    with c:
        chat_id = c.post("/chats", json=NEW).json()["id"]
        present(c, "w1", True, "another")
        present(c, "w2", False, chat_id)  # shows it, but without focus
        c.post(f"/chats/{chat_id}/message", json={"text": "say hi"})
        ended(events)
    assert notifier.sent == [("Claude answered", "say hi")]


def test_a_window_not_heard_from_for_60_s_is_not_focused(hub: Hub, notifier: Recorder) -> None:
    c, events = client(hub)
    with c:
        chats = c.app.state.chats
        now = [100.0]
        chats.clock = lambda: now[0]
        chat_id = c.post("/chats", json=NEW).json()["id"]
        present(c, "w1", True, chat_id)
        now[0] += 59
        assert chats.watched(chat_id)
        now[0] += 1
        assert not chats.watched(chat_id)
        c.post(f"/chats/{chat_id}/message", json={"text": "say hi"})
        ended(events)
    assert len(notifier.sent) == 1


def test_a_blur_or_a_route_change_makes_it_notify(hub: Hub, notifier: Recorder) -> None:
    c, events = client(hub)
    with c:
        chat_id = c.post("/chats", json=NEW).json()["id"]
        present(c, "w1", True, chat_id)
        present(c, "w1", True, None)  # the window went to another screen
        c.post(f"/chats/{chat_id}/message", json={"text": "one"})
        ended(events)
        assert len(notifier.sent) == 1
        present(c, "w1", True, chat_id)
        present(c, "w1", False, chat_id)  # blur
        hub.clock = lambda: hub.waited[(chat_id, "turn")] + 99
        c.post(f"/chats/{chat_id}/message", json={"text": "two"})
        ended(events, 2)
    assert len(notifier.sent) == 2


def test_presence_needs_a_window_and_focused(hub: Hub) -> None:
    c, _ = client(hub)
    assert c.post("/presence", json={"focused": True}).status_code == 422
    assert c.post("/presence", json={"window": "w"}).status_code == 422


def test_a_click_opens_the_app_at_the_chat_and_tells_the_last_focused_window(
    hub: Hub, notifier: Recorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened: list[str] = []
    monkeypatch.setattr(focus, "open_chat", opened.append)
    c, events = client(hub)
    seen: list[dict] = []
    with c:
        chats = c.app.state.chats
        emit = chats.emit
        chats.emit = lambda e: (seen.append(e) if e["type"] == "goto" else None, emit(e))
        chat_id = say(c, "say hi")
        present(c, "w1", True, None)
        present(c, "w2", False, None)  # a window that is not on top does not take the click
        ended(events)
        notifier.clicks[0]()  # notify-send's thread
        until(lambda: seen)
    assert opened == [chat_id]
    assert seen == [{"type": "goto", "window": "w1", "hash": f"#/chat/{chat_id}"}]
