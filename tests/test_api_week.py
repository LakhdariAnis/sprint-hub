import asyncio
from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient

from hubd.api import create_app
from hubd.daemon import Hub

FIXTURE = Path(__file__).parent / "fixtures" / "sprints" / "README.md"
TODAY = date(2026, 11, 5)  # Thursday, 2026-W45


def put_readme(hub: Hub, text: str | None = None) -> Path:
    path = hub.vault / "demo-repo" / "sprint" / "README.md"
    path.write_text(FIXTURE.read_text() if text is None else text)
    return path


def test_week_of_the_fixture(hub: Hub) -> None:
    put_readme(hub)
    week = hub.week(TODAY)
    assert (week["week"], week["days_left"]) == ("2026-W45", 4)
    [current] = week["tracks"]["personal"]
    assert (current["project"], current["name"], current["sprint"]) == ("demo", "demo", 4)
    assert (current["steps_done"], current["steps_total"], current["planned"]) == (0, 0, 10)
    assert week["warnings"] == ["No work sprint in 2026-W45."]


def test_week_counts_the_steps_of_the_sprint(hub: Hub) -> None:
    head = "| Sprint | Track | Week | Goal | Planned | Status |\n|---|---|---|---|---|---|\n"
    put_readme(hub, f"## Sprints\n\n{head}| 1 | work | 2026-W45 | g | 4 h | current |\n")
    mine = [e for e in hub.index.steps if e.project == "demo" and e.step.sprint == 1]
    approved = sum(e.step.state == "approved" for e in mine)
    [row] = hub.week(TODAY)["tracks"]["work"]
    assert (row["steps_done"], row["steps_total"]) == (approved, len(mine))
    assert len(mine) > 1


def test_eta_route_and_unknown_project(hub: Hub) -> None:
    put_readme(hub)
    client = TestClient(create_app(hub))
    body = client.get("/projects/demo/eta").json()
    assert body["data"] is True
    assert client.get("/projects/nope/eta").status_code == 404
    assert client.get("/week").json()["tracks"].keys() == {"work", "personal"}


def test_a_project_without_a_readme_has_no_data(hub: Hub) -> None:
    eta = hub.eta("demo", TODAY)
    assert (eta["data"], eta["sprints"], eta["factor_from"]) == (False, 0, "none")
    errors = TestClient(create_app(hub)).get("/errors").json()
    assert [e for e in errors if e.get("level")] == []  # no README, no warning


def test_bad_rows_are_warnings_in_errors(hub: Hub) -> None:
    path = put_readme(hub)
    warnings = [e for e in TestClient(create_app(hub)).get("/errors").json() if e.get("level")]
    assert len(warnings) == 6
    assert {w["level"] for w in warnings} == {"warning"}
    assert (warnings[0]["path"], warnings[0]["line"]) == (str(path), 21)
    assert "sprint row skipped" in warnings[0]["message"]


def test_a_readme_without_a_table_is_one_warning(hub: Hub) -> None:
    put_readme(hub, "# demo\n\nNo table.\n")
    [warning] = [e for e in TestClient(create_app(hub)).get("/errors").json() if e.get("level")]
    assert "no sprint table" in warning["message"]
    assert hub.week(TODAY)["warnings"] == ["No work sprint in 2026-W45."]  # still answers


def test_saving_the_readme_emits_sprints(hub: Hub) -> None:
    path = put_readme(hub)

    async def main() -> list[str]:
        with hub.subscribe() as queue:
            await hub.reload(path)
            return [queue.get_nowait()["type"] for _ in range(queue.qsize())]

    assert asyncio.run(main()) == ["sprints"]
    assert hub.eta("demo", TODAY)["sprints"] == 3  # sprints 4, 5 and 6 are open
    path.write_text(path.read_text().replace("~14 h", "~24 h"))
    assert hub.eta("demo", TODAY)["raw_hours"] == 34.0  # +10 h at once, no restart
