"""Tests for the team CRUD routes."""

import pytest

from app import teams
from app.team_store import TeamCreate


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    (fake_home / ".hermes").mkdir(parents=True)
    monkeypatch.setattr("app.team_store.TEAMS_PATH", fake_home / ".hermes" / "teams.json")
    return fake_home


def test_create_team_via_route(fake_home):
    created = teams.create_team(
        TeamCreate(display_name="SQL 优化团", description="d", leader="sql", members=["sql", "reviewer"])
    )
    assert created.id == "sql"
    assert created.leader == "sql"
    assert "reviewer" in created.members


def test_create_team_leader_must_be_member(fake_home):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        teams.create_team(TeamCreate(display_name="x", leader="nobody", members=["a"]))
    assert exc_info.value.status_code == 422


def test_create_duplicate_team_409(fake_home):
    from fastapi import HTTPException

    teams.create_team(TeamCreate(display_name="sql", leader="sql", members=["sql"]))
    with pytest.raises(HTTPException) as exc_info:
        teams.create_team(TeamCreate(display_name="sql", leader="sql", members=["sql"]))
    assert exc_info.value.status_code == 409


def test_get_missing_team_404(fake_home):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        teams.get_team("nope")
    assert exc_info.value.status_code == 404


def test_list_teams_from_store(fake_home):
    teams.create_team(TeamCreate(display_name="a", leader="x", members=["x"]))
    teams.create_team(TeamCreate(display_name="b", leader="y", members=["y"]))
    listed = teams.list_teams()
    assert {t.id for t in listed} == {"a", "b"}
    assert listed[0].leader in listed[0].members