"""Tests for the scheduler API routes."""

import pytest

from app.team_store import TeamCreate
from scheduler import api

# Wires engine group-config hook to the team store so sessions get members.
from app.team_store import TeamStore


@pytest.fixture()
def team(tmp_path, monkeypatch):
    monkeypatch.setattr("app.team_store.TEAMS_PATH", tmp_path / "teams.json")
    monkeypatch.setattr("scheduler.db.DB_PATH", tmp_path / "sched.db")
    from app import teams

    if not teams._team_store().load():
        teams._team_store().create(
            TeamCreate(display_name="research", leader="researcher-a",
                       members=["researcher-a", "researcher-b", "reviewer", "writer"])
        )
    # Hook group config (members + leader + confirm flag) into engine.
    api.ensure_group_config_hook()
    return "research"


def test_create_session(team, monkeypatch):
    monkeypatch.setattr("scheduler.api.engine.advance_sessions", lambda: 0)
    sid = api.create_session(team, "调研 AutoGen")
    assert sid.startswith("s_")


def test_get_session(team, monkeypatch):
    fake = {"session_id": "s_1", "group_id": team, "status": "running",
            "user_query": "q", "round_no": 1, "plan_json": "{}",
            "final_report": "", "created_at": "x", "updated_at": "x"}
    monkeypatch.setattr(
        "scheduler.api.db.get_session",
        lambda sid: fake if sid == "s_1" else None,
    )
    monkeypatch.setattr("scheduler.api.db.list_subtasks", lambda *a, **k: [])
    r = api.get_session("s_1")
    assert r["status"] == "running"
    with pytest.raises(Exception) as e:
        api.get_session("nope")
    assert getattr(e.value, "status_code", None) == 404


def test_confirm_plan(team, monkeypatch):
    captured = {}
    from scheduler import db

    db.create_session("s_1", team, "q")
    monkeypatch.setattr(
        "scheduler.api.engine.handle_plan_confirm",
        lambda sid, dec, feedback="": captured.update(sid=sid, dec=dec, fb=feedback),
    )
    monkeypatch.setattr("scheduler.api.db.list_subtasks", lambda *a, **k: [])
    api.confirm_plan("s_1", "confirm", "")
    assert captured["dec"] == "confirm"


def test_resume_session(team, monkeypatch):
    captured = {}
    from scheduler import db

    db.create_session("s_1", team, "q")
    monkeypatch.setattr(
        "scheduler.api.engine.request_resume",
        lambda sid, fb: captured.update(sid=sid, fb=fb),
    )
    monkeypatch.setattr("scheduler.api.db.list_subtasks", lambda *a, **k: [])
    api.resume_session("s_1", "不够深入")
    assert captured["fb"] == "不够深入"