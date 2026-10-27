"""Tests for the expert-team orchestration routes."""

import pytest

from app import teams
from app.hermes_client import HermesError


def test_invoke_calls_team_lead(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "app.teams.run_hermes",
        lambda *args, **kwargs: captured.setdefault("runs", []).append(args) or "",
    )
    monkeypatch.setattr("app.teams.kanban_list", lambda: [])
    monkeypatch.setattr(
        "app.teams.kanban_create", lambda title, **kw: captured.setdefault("created", []).append((title, kw)) or "t_root"
    )
    result = teams.invoke_team("research", "调研多Agent框架")
    assert result["orchestrator_task_id"] == "t_root"
    assert any("team-lead" in str(a) for a in captured.get("runs", []))


def test_invoke_prefers_existing_task_tree(monkeypatch):
    monkeypatch.setattr("app.teams.run_hermes", lambda *a, **k: "")
    monkeypatch.setattr(
        "app.teams.kanban_list",
        lambda: [
            {"id": "t_root", "status": "todo", "parents": []},
            {"id": "t_child", "status": "todo", "parents": ["t_root"]},
        ],
    )
    result = teams.invoke_team("research", "调研")
    assert result["orchestrator_task_id"] == "t_root"


def test_invoke_unknown_team_404():
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        teams.invoke_team("nope", "x")
    assert exc_info.value.status_code == 404


def test_final_reads_metadata(monkeypatch):
    monkeypatch.setattr(
        "app.teams.kanban_list",
        lambda: [
            {
                "id": "t_f",
                "title": "综合报告",
                "status": "done",
                "assignee": "writer",
                "parents": ["t_r"],
            }
        ],
    )
    monkeypatch.setattr(
        "app.teams.kanban_show",
        lambda i: {
            "id": i,
            "title": "综合报告",
            "status": "done",
            "assignee": "writer",
            "metadata": {"final": "# 报告\n内容"},
        },
    )
    result = teams.team_final("research")
    assert result.report == "# 报告\n内容"


def test_final_empty_when_no_done(monkeypatch):
    monkeypatch.setattr("app.teams.kanban_list", lambda: [])
    result = teams.team_final("research")
    assert result.report is None


def test_teams_list_returns_preset():
    result = teams.list_teams()
    assert any(t.id == "research" for t in result)
    team = next(t for t in result if t.id == "research")
    assert "researcher-a" in team.members