import subprocess
import time
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from test_api_chats import until

from hubd.api import create_app
from hubd.daemon import Hub
from hubd.demo import demo_app, demo_vault
from hubd.notify import NullNotifier
from hubd.runners.fake import FakeRunner


def test_demo_vault_is_a_git_repo_without_broken() -> None:
    vault = demo_vault()
    assert not (vault / "projects" / "broken").exists()
    out = subprocess.run(
        ["git", "log", "--format=%D"], cwd=vault / "demo-repo", capture_output=True, text=True
    )
    assert "main" in out.stdout


def test_demo_lists_projects_and_start_runs_fake_runner() -> None:
    with TestClient(demo_app()) as client:
        assert client.get("/health").json()["demo"] is True
        assert [p["id"] for p in client.get("/projects").json()] == ["demo", "notes"]
        states = {
            s["state"] for p in ("demo", "notes") for s in client.get(f"/projects/{p}/steps").json()
        }
        assert states == {"todo", "doing", "done", "changes", "approved"}
        assert client.post("/steps/demo/104/start").json()["state"] == "doing"
        deadline = time.monotonic() + 5
        while client.get("/steps/demo/104").json()["state"] != "done":
            assert time.monotonic() < deadline, "FakeRunner did not end the run"
            time.sleep(0.05)


def test_demo_approve_merges_into_the_demo_repo() -> None:
    with TestClient(demo_app()) as client:
        response = client.post("/steps/demo/103/approve")
        assert response.json()["state"] == "approved"
        repo = client.get("/steps/demo/103").json()["path"].split("/projects/")[0] + "/demo-repo"
    log = subprocess.run(
        ["git", "log", "-1", "--format=%s"], cwd=repo, capture_output=True, text=True
    )
    assert log.stdout.strip() == "Merge branch 'step/103-ui'"


def test_demo_has_two_open_questions() -> None:
    questions = TestClient(demo_app()).get("/questions").json()
    assert [(q["project"], q["step"]) for q in questions] == [("notes", "302")] * 2


def test_demo_has_two_sprints() -> None:
    with TestClient(demo_app()) as client:
        steps = client.get("/projects/demo/steps").json()
        done = {s["state"] for s in steps if s["sprint"] == 2}
        assert done == {"approved"}
        assert {s["sprint"] for s in steps} == {1, 2}


def test_demo_deadlines_overdue_first() -> None:
    with TestClient(demo_app()) as client:
        items = client.get("/deadlines?days=7").json()
    texts = [i["text"] for i in items if i["link"] is None or i["link"] == "demo/104"]
    assert texts == [
        "Compilation TP report",
        "Fraunhofer IPA application",
        "Release notes for the demo",
    ]
    assert items[0]["overdue"] is True
    assert "PFE topic form" not in [i["text"] for i in items]
    # Step `due:` dates follow today too: only the overdue file deadline is late, on any day.
    assert [i["overdue"] for i in items] == [True] + [False] * (len(items) - 1)
    last = (items[-1]["link"], items[-1]["date"])
    assert last == ("notes/301", str(date.today() + timedelta(days=5)))


def test_demo_manual_step_ticks() -> None:
    with TestClient(demo_app()) as client:
        step = client.get("/steps/demo/101").json()
        assert (step["by"], step["state"], len(step["tasks"])) == ("me", "todo", 3)
        assert client.post("/steps/demo/101/tasks/0/tick").json()["state"] == "doing"


def test_demo_has_a_work_and_a_personal_sprint_this_week() -> None:
    from datetime import date

    from hubd.demo import demo_vault

    hub = Hub(demo_vault(), lambda ended: FakeRunner(ended), NullNotifier())
    week = hub.week(date.today())
    assert [r["name"] for r in week["tracks"]["work"]] == ["notes"]
    assert [r["name"] for r in week["tracks"]["personal"]] == ["demo"]
    assert week["warnings"] == []
    assert hub.sprint_tables()[1] == []
    assert hub.eta("demo", date.today())["sprints"] == 2


def test_demo_records_its_popups_and_only_the_demo_serves_them(hub: Hub) -> None:
    with TestClient(demo_app()) as client:
        assert client.get("/demo/notifications").json() == []
        chat_id = client.post("/chats", json={"model": "haiku", "effort": "low"}).json()["id"]
        client.post(f"/chats/{chat_id}/message", json={"text": "say hi"})
        until(lambda: client.get("/demo/notifications").json())
        assert client.get("/demo/notifications").json() == [
            {"title": "Claude answered", "body": "say hi"}
        ]
    assert TestClient(create_app(hub)).get("/demo/notifications").status_code == 404


def test_demo_focus_and_start_never_call_hyprctl(monkeypatch: pytest.MonkeyPatch) -> None:
    def no_process(*a: object, **kw: object) -> None:
        raise AssertionError("demo mode started a process")

    with TestClient(demo_app()) as client:
        projects = {p["id"]: p["workspace"] for p in client.get("/projects").json()}
        assert projects == {"demo": None, "notes": 2}
        monkeypatch.setattr(subprocess, "run", no_process)
        monkeypatch.setattr(subprocess, "Popen", no_process)
        assert client.post("/projects/notes/focus").json() == {"workspace": 2}
        assert client.post("/projects/demo/focus").status_code == 404
        assert client.post("/steps/notes/301/start").status_code == 200


def test_demo_closes_a_sprint() -> None:
    with TestClient(demo_app()) as client:
        r = client.post("/projects/notes/sprints/3/close", json={"own_hours": 2})
        assert (r.status_code, r.json()["moved"], r.json()["next_status"]) == (
            200,
            ["301", "302"],
            "current",
        )
        assert {s["step"]: s["sprint"] for s in client.get("/projects/notes/steps").json()} == {
            "301": 4,
            "302": 4,
        }
        r = client.post("/projects/notes/sprints/4/close")
        assert r.status_code == 409 and "Sprint 5 has no row" in r.json()["detail"]
