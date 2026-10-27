"""Tests for the expert-team orchestration routes."""

import pytest

from app import teams
from app.hermes_client import HermesError


@pytest.fixture(autouse=True)
def _stub_members(monkeypatch):
    """Resolve team members without touching the Hermes CLI."""
    monkeypatch.setattr(
        "app.teams._registered_expert_ids",
        lambda: ["researcher-a", "researcher-b", "reviewer", "writer"],
    )


def test_invoke_builds_task_tree(monkeypatch):
    """invoke deterministically builds the 4-task dependency tree."""
    created = []
    monkeypatch.setattr(
        "app.teams.run_hermes",
        lambda *args, **kwargs: "",
    )
    monkeypatch.setattr(
        "app.teams.kanban_create",
        lambda title, **kw: created.append((title, kw)) or f"t_{len(created) - 1}",
    )
    result = teams.invoke_team("research", "调研多Agent框架")
    # 4 tasks must be created; final (writer) task returned (id t_3).
    assert len(created) == 4
    assert result["orchestrator_task_id"] == "t_3"
    # writer task (index 3) must depend on review task (index 2).
    assert created[3][1]["parent_ids"] == ["t_2"]
    # review task depends on tech + case.
    assert set(created[2][1]["parent_ids"]) == {"t_0", "t_1"}
    assert created[0][1]["assignee"] == "researcher-a"
    assert created[1][1]["assignee"] == "researcher-b"
    assert created[2][1]["assignee"] == "reviewer"
    assert created[3][1]["assignee"] == "writer"


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