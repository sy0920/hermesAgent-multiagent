"""Tests for the persistent team store (teams.json CRUD)."""

import pytest

from app.team_store import TeamCreate, TeamStore


def test_load_empty_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("app.team_store.TEAMS_PATH", tmp_path / "teams.json")
    s = TeamStore()
    assert s.load() == []


def test_create_and_load_roundtrip(tmp_path, monkeypatch):
    p = tmp_path / "teams.json"
    monkeypatch.setattr("app.team_store.TEAMS_PATH", p)
    s = TeamStore()
    t = s.create(
        TeamCreate(
            display_name="SQL 优化团",
            description="慢 SQL 诊断",
            leader="sql",
            members=["sql", "reviewer", "writer"],
        )
    )
    assert t.id == "sql"  # slug of "SQL 优化团"
    reloaded = TeamStore().load()
    assert reloaded[0].id == "sql"
    assert reloaded[0].leader == "sql"
    assert "reviewer" in reloaded[0].members


def test_create_duplicate_raises(tmp_path, monkeypatch):
    p = tmp_path / "teams.json"
    monkeypatch.setattr("app.team_store.TEAMS_PATH", p)
    s = TeamStore()
    s.create(TeamCreate(display_name="a", leader="x", members=["x"]))
    with pytest.raises(ValueError, match="already exists"):
        s.create(TeamCreate(display_name="a", leader="x", members=["x"]))


def test_create_pure_chinese_generates_id(tmp_path, monkeypatch):
    p = tmp_path / "teams.json"
    monkeypatch.setattr("app.team_store.TEAMS_PATH", p)
    s = TeamStore()
    t = s.create(TeamCreate(display_name="文档评审团", leader="r", members=["r"]))
    assert t.id.startswith("team-")


def test_get_returns_team_or_none(tmp_path, monkeypatch):
    p = tmp_path / "teams.json"
    monkeypatch.setattr("app.team_store.TEAMS_PATH", p)
    s = TeamStore()
    s.create(TeamCreate(display_name="sql", leader="sql", members=["sql"]))
    assert s.get("sql") is not None
    assert s.get("nope") is None