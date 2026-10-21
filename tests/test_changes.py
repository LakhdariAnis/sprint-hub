import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hubd.api import create_app
from hubd.daemon import Hub
from hubd.model import Review, State
from hubd.states import InvalidTransition
from hubd.vault import _load_step

STEP_103 = Path("projects") / "demo" / "steps" / "103.md"


def test_comment_saved_without_breaking_the_file(vault: Path, hub: Hub) -> None:
    before = (vault / STEP_103).read_text()
    step = asyncio.run(hub.request_changes("demo", "103", "Add a test for the empty list"))
    assert step.state == State.changes
    text = (vault / STEP_103).read_text()
    assert text == before.replace("state: done   #", "state: changes   #").replace(
        "verdict:\ncomment:\n",
        "verdict: changes\ncomment: Add a test for the empty list\n",
    )
    saved = _load_step(vault / STEP_103)
    assert saved.review == Review(verdict="changes", comment="Add a test for the empty list")


def test_changes_only_from_done(vault: Path, hub: Hub) -> None:
    before = (vault / "projects" / "demo" / "steps" / "104.md").read_text()
    with pytest.raises(InvalidTransition, match="no 'request_changes' from 'changes'"):
        asyncio.run(hub.request_changes("demo", "104", "nope"))
    assert (vault / "projects" / "demo" / "steps" / "104.md").read_text() == before


def test_changes_api(vault: Path, hub: Hub) -> None:
    client = TestClient(create_app(hub))
    response = client.post("/steps/demo/103/changes", json={"comment": "Rename the list"})
    assert response.status_code == 200
    assert response.json()["review"] == {"verdict": "changes", "comment": "Rename the list"}
    assert _load_step(vault / STEP_103).state == State.changes
    again = client.post("/steps/demo/103/changes", json={"comment": "again"})
    assert again.status_code == 409
    assert again.json() == {"detail": "step 103: no 'request_changes' from 'changes'"}
    assert client.post("/steps/demo/999/changes", json={"comment": "x"}).status_code == 404


@pytest.mark.parametrize("comment", ["", "   ", "two\nlines"])
def test_changes_api_needs_one_line(vault: Path, hub: Hub, comment: str) -> None:
    before = (vault / STEP_103).read_text()
    response = TestClient(create_app(hub)).post(
        "/steps/demo/103/changes", json={"comment": comment}
    )
    assert response.status_code == 422
    assert (vault / STEP_103).read_text() == before


def test_next_start_resumes_with_the_comment(vault: Path, hub: Hub) -> None:
    (vault / "demo-repo" / "sprint" / "103-ui.md").write_text("# Step 103\n\n## Tasks\n- Sort\n")

    async def main() -> None:
        await hub.request_changes("demo", "103", "Sort the list")
        step = await hub.start("demo", "103")
        assert hub.runner.resumed == [("7b1e…a04", "Sort the list")]
        assert [(r.session, r.model) for r in step.runs] == [("7b1e…a04", "sonnet")] * 2
        await hub.runner.tasks["7b1e…a04"]

    asyncio.run(main())
    saved = _load_step(vault / STEP_103)
    assert saved.state == State.done
    assert len(saved.runs) == 2


def test_start_from_todo_is_a_new_chat(hub: Hub) -> None:
    async def main() -> None:
        hub.entry("demo", "104").step.state = State.todo
        step = await hub.start("demo", "104")
        assert hub.runner.resumed == []
        assert step.runs[-1].session != "9c3d…e12"

    asyncio.run(main())
