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


def event(**fields: object) -> io.StringIO:
    return io.StringIO(json.dumps({**json.loads(SAMPLE), **fields}))


ENV = {"HUB_RUN": "106", "HUB_URL": "http://127.0.0.1:9"}
SESSION = "d1e48e65-7771-418b-9a6d-2188084da351"


def test_stop_posts_a_turn(posts: list[urllib.request.Request]) -> None:
    assert hook.main(event(hook_event_name="Stop", stop_hook_active=False), ENV) == 0
    [request] = posts
    assert request.full_url == "http://127.0.0.1:9/runs/waiting"
    assert json.loads(request.data) == {"session_id": SESSION, "step": "106", "kind": "turn"}


def test_stop_from_a_stop_hook_is_skipped(posts: list[urllib.request.Request]) -> None:
    assert hook.main(event(hook_event_name="Stop", stop_hook_active=True), ENV) == 0
    assert posts == []


@pytest.mark.parametrize(
    ("kind", "sent"), [("permission_prompt", "permission"), ("idle_prompt", "idle")]
)
def test_notification_posts_its_kind(
    posts: list[urllib.request.Request], kind: str, sent: str
) -> None:
    assert hook.main(event(hook_event_name="Notification", notification_type=kind), ENV) == 0
    [request] = posts
    assert request.full_url == "http://127.0.0.1:9/runs/waiting"
    assert json.loads(request.data)["kind"] == sent


def test_other_notification_sends_nothing(posts: list[urllib.request.Request]) -> None:
    assert (
        hook.main(event(hook_event_name="Notification", notification_type="auth_success"), ENV) == 0
    )
    assert hook.main(event(hook_event_name="Notification"), ENV) == 0
    assert posts == []


@pytest.mark.parametrize("name", ["Stop", "Notification"])
def test_new_events_outside_a_hub_run(posts: list[urllib.request.Request], name: str) -> None:
    fields = {"hook_event_name": name, "notification_type": "permission_prompt"}
    assert hook.main(event(**fields), {}) == 0
    assert posts == []


def test_new_events_with_hubd_down() -> None:
    env = {"HUB_RUN": "106", "HUB_URL": "http://127.0.0.1:1"}
    assert hook.main(event(hook_event_name="Stop"), env) == 0
    assert (
        hook.main(event(hook_event_name="Notification", notification_type="idle_prompt"), env) == 0
    )


def test_odd_json_exits_quietly(posts: list[urllib.request.Request]) -> None:
    assert hook.main(io.StringIO("[]"), ENV) == 0
    assert hook.main(io.StringIO('"x"'), ENV) == 0
    assert posts == []
