"""Popups of a chat that answers or asks (612b), with FakeChat."""

from conftest import Recorder
from fastapi.testclient import TestClient
from test_api_chats import NEW, asked, client, until

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
