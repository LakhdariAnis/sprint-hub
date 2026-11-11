"""The chat routes with FakeChat: open, messages, stop, `chat` events, bad bodies."""

import json
import time
from collections.abc import Callable
from pathlib import Path

import httpx2
from fastapi.testclient import TestClient
from test_sse import serve

from hubd.api import create_app
from hubd.daemon import Hub
from hubd.runners.fake import REPLY, FakeChat

NEW = {"model": "haiku", "effort": "low"}


def until(done: Callable[[], bool]) -> None:
    deadline = time.monotonic() + 5
    while not done():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.01)


def client(hub: Hub, delay: float = 0) -> tuple[TestClient, list[dict]]:
    """A client and the `chat` events hubd emitted."""
    events: list[dict] = []
    emit = hub.emit
    hub.emit = lambda e: (events.append(e) if e["type"] == "chat" else None, emit(e))
    return TestClient(create_app(hub, chat=lambda on: FakeChat(on, delay=delay))), events


def test_open_and_two_messages(vault: Path, hub: Hub) -> None:
    c, events = client(hub)
    with c:
        chat_id = c.post("/chats", json=NEW).json()["id"]
        for n in (1, 2):
            assert c.post(f"/chats/{chat_id}/message", json={"text": f"hi {n}"}).status_code == 200
            until(lambda n=n: [e["kind"] for e in events].count("turn_end") == n)
        chat = c.get(f"/chats/{chat_id}").json()
    assert chat["cwd"] == str(vault / "chats" / "scratch") and chat["project"] is None
    assert chat["live"] and not chat["busy"]
    assert [t["text"] for t in chat["turns"]] == ["hi 1", "hi 2"]
    kinds = [e["kind"] for e in chat["turns"][0]["events"]]
    assert kinds == ["text", "tool", "tool_result", "text", "turn_end"]  # deltas joined
    texts = [e["text"] for e in chat["turns"][1]["events"] if e["kind"] == "text"]
    assert "".join(texts) == "".join(REPLY)
    assert all(e["id"] == chat_id for e in events)
    assert events[0] == {"type": "chat", "id": chat_id, "kind": "text", "text": REPLY[0]}
    tool = chat["turns"][0]["events"][1]
    assert tool == {"kind": "tool", "tool_id": "fake_tool", "name": "Bash", "input": "ls"}


def test_project_chat_runs_in_its_repo(vault: Path, hub: Hub) -> None:
    c, _ = client(hub)
    chat_id = c.post("/chats", json=NEW | {"project": "demo"}).json()["id"]
    assert c.get(f"/chats/{chat_id}").json()["cwd"] == str(hub.repo("demo"))


def test_stop_mid_turn(hub: Hub) -> None:
    c, events = client(hub, delay=0.2)
    with c:
        chat_id = c.post("/chats", json=NEW).json()["id"]
        c.post(f"/chats/{chat_id}/message", json={"text": "a long one"})
        until(lambda: any(e["kind"] == "text" for e in events))
        assert c.get(f"/chats/{chat_id}").json()["busy"]
        assert c.post(f"/chats/{chat_id}/stop").status_code == 200
        chat = c.get(f"/chats/{chat_id}").json()
        time.sleep(0.3)  # nothing more comes after the stop
    assert events[-1]["kind"] == "stopped"
    assert "turn_end" not in [e["kind"] for e in events]
    assert not chat["live"] and not chat["busy"]
    assert chat["turns"][0]["events"][-1] == {"kind": "stopped"}


def test_bad_bodies_are_422(hub: Hub) -> None:
    c, _ = client(hub)
    chat_id = c.post("/chats", json=NEW).json()["id"]
    for body in ({"text": ""}, {"text": "  \n"}, {}):
        assert c.post(f"/chats/{chat_id}/message", json=body).status_code == 422
    for body in (NEW | {"model": "gpt"}, NEW | {"effort": "huge"}, {"model": "haiku"}):
        assert c.post("/chats", json=body).status_code == 422
    response = c.post("/chats", json=NEW | {"project": "nope"})
    assert response.status_code == 422
    assert response.json() == {"detail": "no project nope"}
    assert c.post("/chats/nope/message", json={"text": "hi"}).status_code == 404
    assert c.get("/chats/nope").status_code == 404


def test_chat_events_stream_on_events(hub: Hub) -> None:
    app = create_app(hub, chat=lambda on: FakeChat(on, delay=0))
    kinds: list[str] = []
    with serve(app) as url, httpx2.stream("GET", f"{url}/events", timeout=5) as response:
        lines = response.iter_lines()
        assert next(lines) == ": connected"
        chat_id = httpx2.post(f"{url}/chats", json=NEW).json()["id"]
        httpx2.post(f"{url}/chats/{chat_id}/message", json={"text": "say hi"})
        for line in lines:
            if line == "event: chat":
                continue
            if line.startswith("data: "):
                event = json.loads(line.removeprefix("data: "))
                if event["type"] == "chat":
                    assert event["id"] == chat_id
                    kinds.append(event["kind"])
                    if event["kind"] == "turn_end":
                        break
    assert kinds[0] == "text" and kinds[-1] == "turn_end" and "tool" in kinds
