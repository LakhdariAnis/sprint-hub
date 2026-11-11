"""FakeChat follows the ChatRunner protocol with no Claude."""

import asyncio
from pathlib import Path
from typing import Any

from hubd.runners.fake import REPLY, FakeChat

ID = "8f6a0c2e-3b1d-4c5e-9f7a-1b2c3d4e5f60"


def chat() -> tuple[FakeChat, asyncio.Queue[tuple[str, dict[str, Any]]]]:
    events: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue()

    async def on_event(chat_id: str, event: dict[str, Any]) -> None:
        await events.put((chat_id, event))

    return FakeChat(on_event, delay=0), events


async def turn(events: asyncio.Queue) -> list[dict[str, Any]]:
    seen: list[dict[str, Any]] = []
    while not seen or seen[-1]["type"] != "turn_end":
        chat_id, event = await asyncio.wait_for(events.get(), 5)
        assert chat_id == ID
        seen.append(event)
    return seen


def test_two_turns_each_stream_the_reply_and_a_tool_call() -> None:
    async def main() -> None:
        fake, events = chat()
        await fake.open(ID, Path("."), "haiku", None)
        for text in ("one", "two"):
            await fake.send(ID, text)
            seen = await turn(events)
            assert [e["type"] for e in seen] == (
                ["text"] * 3 + ["tool", "tool_result"] + ["text"] * 2 + ["turn_end"]
            )
            assert "".join(e["text"] for e in seen if e["type"] == "text") == "".join(REPLY)
        assert events.empty()

    asyncio.run(main())


def test_stop_mid_turn_ends_it_without_turn_end_and_open_resumes() -> None:
    async def main() -> None:
        fake, events = chat()
        fake.delay = 0.05
        await fake.open(ID, Path("."), "haiku", None)
        await fake.send(ID, "one")
        assert (await events.get())[1]["type"] == "text"
        await fake.stop(ID)
        while not events.empty():
            assert events.get_nowait()[1]["type"] != "turn_end"
        await asyncio.sleep(0.2)
        assert events.empty()
        await fake.send(ID, "closed")  # not open any more
        assert (await events.get())[1] == {"type": "error", "message": "chat is not open"}
        await fake.open(ID, Path("."), "haiku", None)
        fake.delay = 0
        await fake.send(ID, "again")
        assert (await turn(events))[-1]["type"] == "turn_end"

    asyncio.run(main())
