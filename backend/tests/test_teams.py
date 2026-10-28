"""Tests for the expert-team orchestration routes (Team model based)."""

import pytest

from app import teams
from app.hermes_client import HermesError
from app.team_store import TeamCreate


@pytest.fixture(autouse=True)
def _temp_team_store(tmp_path, monkeypatch):
    """Point teams.json at a temp file and pre-create a 'research' team."""
    fake_home = tmp_path / "home"
    (fake_home / ".hermes").mkdir(parents=True)
    p = fake_home / ".hermes" / "teams.json"
    monkeypatch.setattr("app.team_store.TEAMS_PATH", p)
    teams._team_store().create(
        TeamCreate(
            display_name="research",
            leader="researcher-a",
            members=["researcher-a", "researcher-b", "reviewer", "writer"],
        )
    )


def test_invoke_builds_task_tree(monkeypatch):
    """invoke deterministically builds the 4-task dependency tree."""
    created = []
    monkeypatch.setattr(
        "app.teams.expert_chat",
        lambda p, m, session_id=None: ("", None),  # planner silent → fallback
    )
    monkeypatch.setattr(
        "app.teams.kanban_create",
        lambda title, **kw: created.append((title, kw)) or f"t_{len(created) - 1}",
    )
    result = teams.invoke_team("research", "调研多Agent框架")
    # 4 tasks must be created; final task (id t_3) returned when planner silent.
    assert len(created) == 4
    assert result["orchestrator_task_id"] == "t_3"
    assert set(created[2][1]["parent_ids"]) == {"t_0", "t_1"}
    # The leader (researcher-a) must not appear as any assignee.
    assignees = set(a for _, kw in created if (a := kw.get("assignee")))
    assert "researcher-a" not in assignees


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


def test_teams_list_contains_preset():
    result = teams.list_teams()
    assert any(t.id == "research" for t in result)
    team = next(t for t in result if t.id == "research")
    assert team.leader == "researcher-a"
    assert "writer" in team.members