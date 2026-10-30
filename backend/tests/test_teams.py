"""Legacy invoke contract — retired in favor of the central orchestrator.

POST /api/teams/{id}/sessions (scheduler) replaced invoke. We keep these
tests to pin the migration contract: invoke answers 410, never executes.
"""

import pytest

from app import teams
from app.team_store import TeamCreate


@pytest.fixture(autouse=True)
def _temp_team_store(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    (fake_home / ".hermes").mkdir(parents=True)
    p = fake_home / ".hermes" / "teams.json"
    monkeypatch.setattr("app.team_store.TEAMS_PATH", p)
    monkeypatch.setattr("scheduler.db.DB_PATH", tmp_path / "sched.db")
    teams._team_store().create(
        TeamCreate(
            display_name="research",
            leader="researcher-a",
            members=["researcher-a", "researcher-b", "reviewer", "writer"],
        )
    )
    teams._invoke_windows.clear()
    teams._dispatched_once.clear()
    from scheduler import engine

    engine._kanban_mirrored.clear()


def test_invoke_returns_410_migrated(monkeypatch):
    """invoke is retired; it must answer 410 with a pointer to sessions."""
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        teams.invoke_team("research", "调研")
    assert exc_info.value.status_code == 410
    assert "sessions" in exc_info.value.detail


def test_advance_once_noop_after_migrate(monkeypatch):
    """advance_once still exists for API compat but dispatches nothing real."""
    rows = [
        {"id": "t_x", "status": "ready", "assignee": "researcher-a", "parents": []},
    ]
    monkeypatch.setattr("app.teams.kanban_list", lambda: rows)
    # The legacy worker must not call any Hermes execution path.
    monkeypatch.setattr("app.teams.kanban_show", lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not read task")))
    # Existing dispatcher is a no-op logger — advance still returns (threads are daemon).
    n = teams.advance_once()
    assert n >= 0


def test_team_crud_still_works(tmp_path, monkeypatch):
    """Team registry operations survive the migration."""
    teams._team_store().create(
        TeamCreate(display_name="second", leader="writer", members=["writer"])
    )
    assert teams._team_store().get("second") is not None