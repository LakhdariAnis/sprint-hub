from pathlib import Path

from fastapi.testclient import TestClient
from test_api_chats import until

from hubd.api import create_app
from hubd.daemon import Hub
from hubd.settings import load_settings

GOOD = {"terminal": ["foot", "--working-directory={cwd}"], "reminder_hour": 8}


def toml(hub: Hub) -> Path:
    return hub.vault / "hub.toml"


def test_get_defaults(hub: Hub) -> None:
    body = TestClient(create_app(hub)).get("/settings").json()
    assert body == {
        "path": str(toml(hub)),
        "terminal": ["xdg-terminal-exec", "--dir={cwd}"],
        "reminder_hour": 9,
        "notify_waiting": True,
        "error": None,
        "comments": False,
        "restart": [],
    }


def test_put_saves_and_applies(hub: Hub) -> None:
    toml(hub).write_text("# mine\nreminder_hour = 7\n")
    client = TestClient(create_app(hub, reminder_hour=7))
    assert client.get("/settings").json()["comments"] is True
    response = client.put("/settings", json=GOOD)
    assert response.status_code == 200
    assert response.json()["reminder_hour"] == 8
    assert load_settings(toml(hub)).terminal == GOOD["terminal"]
    assert client.get("/settings").json()["terminal"] == GOOD["terminal"]
    assert client.get("/settings").json()["comments"] is False


def test_bad_values_are_refused_and_the_file_stays(hub: Hub) -> None:
    toml(hub).write_text("reminder_hour = 7\n")
    client = TestClient(create_app(hub))
    for bad, text in (
        ({**GOOD, "reminder_hour": 99}, "reminder_hour: must be 0–23"),
        ({**GOOD, "terminal": ["foot"]}, "terminal: must contain {cwd}"),
        ({**GOOD, "terminal": "foot {cwd}"}, "terminal: "),
        ({**GOOD, "reminder_hour": "late"}, "reminder_hour: "),
    ):
        response = client.put("/settings", json=bad)
        assert response.status_code == 422
        assert text in response.json()["detail"]
    assert toml(hub).read_text() == "reminder_hour = 7\n"
    assert client.get("/settings").json()["reminder_hour"] == 7


def test_broken_file_shows_defaults_and_the_error_then_a_save_heals_it(hub: Hub) -> None:
    toml(hub).write_text("broken = [\n")
    client = TestClient(create_app(hub))
    body = client.get("/settings").json()
    assert body["terminal"] == ["xdg-terminal-exec", "--dir={cwd}"]
    assert body["error"].startswith(str(toml(hub)))
    assert client.put("/settings", json=GOOD).json()["error"] is None
    assert load_settings(toml(hub)).reminder_hour == 8


def test_put_reaches_the_runner(hub: Hub) -> None:
    hub.runner.terminal = ["old", "{cwd}"]
    app = create_app(hub)
    TestClient(app).put("/settings", json=GOOD)
    assert hub.runner.terminal == GOOD["terminal"]


def test_notify_waiting_off_sends_nothing(hub: Hub, notifier) -> None:
    client = TestClient(create_app(hub))
    off = client.put("/settings", json={**GOOD, "notify_waiting": False})
    assert off.json()["notify_waiting"] is False
    assert load_settings(toml(hub)).notify_waiting is False
    body = {"session_id": "3f2a…c91", "step": "102", "kind": "turn"}
    assert client.post("/runs/waiting", json=body).json() == {"sent": False}
    assert notifier.sent == []
    client.put("/settings", json={**GOOD, "notify_waiting": True})
    assert client.post("/runs/waiting", json=body).json() == {"sent": True}


def test_notify_waiting_off_also_silences_chats(hub: Hub, notifier) -> None:
    client = TestClient(create_app(hub))
    client.put("/settings", json={**GOOD, "notify_waiting": False})
    with client:
        chat_id = client.post("/chats", json={"model": "haiku", "effort": "low"}).json()["id"]
        client.post(f"/chats/{chat_id}/message", json={"text": "say hi"})
        until(lambda: not client.get(f"/chats/{chat_id}").json()["busy"])
        assert notifier.sent == []
        client.put("/settings", json={**GOOD, "notify_waiting": True})
        client.post(f"/chats/{chat_id}/message", json={"text": "again"})
        until(lambda: notifier.sent)
    assert notifier.sent == [("Claude answered", "say hi")]
