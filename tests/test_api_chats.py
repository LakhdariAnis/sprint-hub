"""The chat routes with FakeChat: open, messages, stop, `chat` events, bad bodies."""

import json
import time
from collections.abc import Callable
from pathlib import Path

import httpx2
from fastapi.testclient import TestClient
from test_sse import serve

from hubd.api import create_app
from hubd.chats import IDLE
from hubd.daemon import Hub
from hubd.runners.chat import ChatEvent
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


def test_cap_of_three_live_chats(hub: Hub) -> None:
    c, events = client(hub)
    with c:
        ids = [c.post("/chats", json=NEW).json()["id"] for _ in range(3)]
        for chat_id in ids:
            c.post(f"/chats/{chat_id}/message", json={"text": "hi"})
        until(lambda: [e["kind"] for e in events].count("turn_end") == 3)
        response = c.post("/chats", json=NEW)
        assert response.status_code == 409
        assert response.json()["detail"].startswith("3 chats are open already (")
        assert response.json()["detail"].endswith("): stop one first")
        c.post(f"/chats/{ids[0]}/stop")
        fourth = c.post("/chats", json=NEW)
        assert fourth.status_code == 200
        # The stopped chat can't come back while 3 others are live.
        again = c.post(f"/chats/{ids[0]}/message", json={"text": "back"})
        assert again.status_code == 409
        assert c.get(f"/chats/{ids[0]}").json()["turns"][-1]["text"] == "hi"  # nothing kept


def test_idle_close_then_resume(hub: Hub) -> None:
    c, events = client(hub)
    with c:
        chats = c.app.state.chats
        busy = c.post("/chats", json=NEW).json()["id"]
        quiet = c.post("/chats", json=NEW).json()["id"]
        c.post(f"/chats/{quiet}/message", json={"text": "hi"})
        until(lambda: "turn_end" in [e["kind"] for e in events])
        c.portal.call(chats.close_idle, time.monotonic(), 60)  # not idle yet
        assert c.get(f"/chats/{quiet}").json()["live"]
        chats.chats[busy].turns.append({"text": "slow", "events": [], "done": False})
        c.portal.call(chats.close_idle, time.monotonic() + IDLE)
        assert events[-1] == {"type": "chat", "id": quiet, "kind": "closed"}
        assert not c.get(f"/chats/{quiet}").json()["live"]
        assert c.get(f"/chats/{busy}").json()["live"]  # a turn under way is not idle
        c.post(f"/chats/{quiet}/message", json={"text": "again"})
        until(lambda: [e["kind"] for e in events].count("turn_end") == 2)
        chat = c.get(f"/chats/{quiet}").json()
    assert chat["live"] and [t["text"] for t in chat["turns"]] == ["hi", "again"]


def test_shutdown_closes_every_process(hub: Hub) -> None:
    runners: list[FakeChat] = []

    def make(on: ChatEvent) -> FakeChat:
        runners.append(FakeChat(on, delay=0.2))
        return runners[-1]

    with TestClient(create_app(hub, chat=make)) as c:
        ids = [c.post("/chats", json=NEW).json()["id"] for _ in range(2)]
        c.post(f"/chats/{ids[0]}/message", json={"text": "a long one"})
        assert runners[0].chats == set(ids)
    assert runners[0].chats == set() and runners[0].turns == {}


def test_patch_resumes_with_the_new_model(hub: Hub) -> None:
    c, events = client(hub)
    with c:
        runner = c.app.state.chats.runner
        chat_id = c.post("/chats", json=NEW).json()["id"]
        c.post(f"/chats/{chat_id}/message", json={"text": "first"})
        until(lambda: [e["kind"] for e in events].count("turn_end") == 1)
        response = c.patch(f"/chats/{chat_id}", json={"model": "opus"})
        assert response.status_code == 200
        assert (response.json()["model"], response.json()["effort"]) == ("opus", "low")
        assert runner.opened == [(chat_id, "haiku", "low"), (chat_id, "opus", "low")]
        c.patch(f"/chats/{chat_id}", json={"effort": "high"})
        assert runner.opened[-1] == (chat_id, "opus", "high")
        c.post(f"/chats/{chat_id}/message", json={"text": "second"})
        until(lambda: [e["kind"] for e in events].count("turn_end") == 2)
        assert [t["text"] for t in c.get(f"/chats/{chat_id}").json()["turns"]] == [
            "first",
            "second",
        ]


def test_patch_refused_mid_turn_or_bad(hub: Hub) -> None:
    c, events = client(hub, delay=0.2)
    with c:
        chat_id = c.post("/chats", json=NEW).json()["id"]
        c.post(f"/chats/{chat_id}/message", json={"text": "slow"})
        response = c.patch(f"/chats/{chat_id}", json={"model": "opus"})
        assert response.status_code == 409 and "answering" in response.json()["detail"]
        assert c.get(f"/chats/{chat_id}").json()["model"] == "haiku"
        assert c.patch(f"/chats/{chat_id}", json={"model": "gpt"}).status_code == 422
        assert c.patch("/chats/nope", json={"model": "opus"}).status_code == 404
        until(lambda: any(e["kind"] == "turn_end" for e in events))


def test_step_chat_is_told_its_context_on_every_open(hub: Hub) -> None:
    (hub.repo("demo") / "README.md").write_text("# Demo\n\nThe demo pitch.\n")
    c, events = client(hub)
    with c:
        runner = c.app.state.chats.runner
        body = NEW | {"project": "demo", "step": "102"}
        opened = c.post("/chats", json=body).json()
        chat_id = opened["id"]
        system = runner.systems[0]
        assert "The demo pitch." in system and "## Step 102" in system
        assert "sprint/progress/102.md" in system
        context = c.get(f"/chats/{chat_id}").json()["context"]
        assert context["label"] == "spec + checklist + README" and context["size"] > 0
        assert "no sprint/PROGRESS.md" in context["notes"]
        assert opened["context"] == context
        c.post(f"/chats/{chat_id}/stop")
        c.post(f"/chats/{chat_id}/message", json={"text": "hi"})  # resumes the process
        until(lambda: [e["kind"] for e in events].count("turn_end") == 1)
        c.patch(f"/chats/{chat_id}", json={"model": "opus"})
        assert runner.systems == [system] * 3


def test_context_preview_and_plain_chats(hub: Hub) -> None:
    c, _ = client(hub)
    with c:
        preview = c.get("/projects/demo/context", params={"sprint": 1}).json()
        assert preview["label"] == "" and preview["size"] > 0
        assert preview["notes"] == ["no sprint/README.md", "no README.md"]  # notes, not errors
        assert c.get("/projects/nope/context").status_code == 404
        assert c.get("/projects/demo/context", params={"step": "999"}).status_code == 404
        chat_id = c.post("/chats", json=NEW).json()["id"]
        assert c.app.state.chats.runner.systems == [None]
        assert c.get(f"/chats/{chat_id}").json()["context"] is None
