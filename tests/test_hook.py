import io
import json
import urllib.request
from pathlib import Path

import pytest

from hubd import hook

SAMPLE = (Path(__file__).parent / "fixtures" / "hook" / "session-end.json").read_text()


@pytest.fixture
def posts(monkeypatch: pytest.MonkeyPatch) -> list[urllib.request.Request]:
    sent: list[urllib.request.Request] = []

    def urlopen(request: urllib.request.Request, timeout: float) -> io.BytesIO:
        sent.append(request)
        return io.BytesIO()

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    return sent


def test_fixture_is_a_session_end_event() -> None:
    event = json.loads(SAMPLE)
    assert event["hook_event_name"] == "SessionEnd"
    assert event["session_id"]


def test_posts_session_and_step(posts: list[urllib.request.Request]) -> None:
    env = {"HUB_RUN": "106", "HUB_URL": "http://127.0.0.1:9"}
    assert hook.main(io.StringIO(SAMPLE), env) == 0
    [request] = posts
    assert request.full_url == "http://127.0.0.1:9/runs/ended"
    assert request.get_method() == "POST"
    assert json.loads(request.data) == {
        "session_id": "d1e48e65-7771-418b-9a6d-2188084da351",
        "step": "106",
    }


def test_no_hub_run_no_post(posts: list[urllib.request.Request]) -> None:
    assert hook.main(io.StringIO(SAMPLE), {}) == 0
    assert posts == []


def test_hubd_down_exits_quietly() -> None:
    env = {"HUB_RUN": "106", "HUB_URL": "http://127.0.0.1:1"}  # nothing listens on port 1
    assert hook.main(io.StringIO(SAMPLE), env) == 0


def test_bad_input_exits_quietly(posts: list[urllib.request.Request]) -> None:
    assert hook.main(io.StringIO("not json"), {"HUB_RUN": "106"}) == 0
    assert hook.main(io.StringIO("{}"), {"HUB_RUN": "106"}) == 0
    assert posts == []
