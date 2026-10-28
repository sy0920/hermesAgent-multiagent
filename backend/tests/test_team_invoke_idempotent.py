"""Tests for team invoke idempotency (no duplicate task trees)."""

import pytest

from app import teams
from app.hermes_client import HermesError
from app.team_store import TeamCreate


@pytest.fixture(autouse=True)
def _temp_team_store(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    (fake_home / ".hermes").mkdir(parents=True)
    p = fake_home / ".hermes" / "teams.json"
    monkeypatch.setattr("app.team_store.TEAMS_PATH", p)
    teams._team_store().create(
        TeamCreate(
            display_name="agent",
            leader="researcher-a",
            members=["researcher-a", "researcher-b", "reviewer", "writer"],
        )
    )


def test_invoke_returns_existing_active_task(monkeypatch):
    """Re-invoking while the team already has active tasks reuses them."""
    calls = {"kanban_create": 0}
    monkeypatch.setattr(
        "app.teams.expert_chat",
        lambda p, m, session_id=None: ("", None),
    )
    monkeypatch.setattr(
        "app.teams.kanban_create",
        lambda title, **kw: calls.__setitem__("kanban_create", calls["kanban_create"] + 1) or f"t_{calls['kanban_create'] - 1}",
    )
    # First invoke: no active tasks → creates the tree.
    monkeypatch.setattr("app.teams.kanban_list", lambda: [])
    first = teams.invoke_team("agent", "调研 AutoGen")
    created_after_first = calls["kanban_create"]
    # There are now active tasks with the team's assignees; second invoke no-ops.
    rows = [
        {"id": "t_0", "status": "ready", "assignee": "researcher-b", "parents": []},
        {"id": "t_1", "status": "todo", "assignee": "reviewer", "parents": ["t_0"]},
    ]
    monkeypatch.setattr("app.teams.kanban_list", lambda: rows)
    second = teams.invoke_team("agent", "调研 AutoGen 第二次")
    assert calls["kanban_create"] == created_after_first, "must not create duplicates"
    assert second["orchestrator_task_id"] == "t_0"


def test_invoke_new_tree_when_no_active(monkeypatch):
    """After all tasks complete, a fresh invoke creates a new tree."""
    calls = {"kanban_create": 0}
    monkeypatch.setattr(
        "app.teams.expert_chat",
        lambda p, m, session_id=None: ("", None),
    )
    monkeypatch.setattr(
        "app.teams.kanban_create",
        lambda title, **kw: calls.__setitem__("kanban_create", calls["kanban_create"] + 1) or f"t_{calls['kanban_create'] - 1}",
    )
    calls["kanban_create"] = 0
    # No active tasks (all done or none) → new tree allowed.
    monkeypatch.setattr(
        "app.teams.kanban_list",
        lambda: [{"id": "t_done", "status": "done", "assignee": "researcher-b", "parents": []}],
    )
    result = teams.invoke_team("agent", "新需求")
    assert calls["kanban_create"] == 4
    assert result["orchestrator_task_id"] == "t_3"


def test_concurrent_invokes_build_one_tree(monkeypatch):
    """Two simultaneous invokes must serialize: only one tree is built."""
    import threading

    calls = {"kanban_create": 0, "trees": 0}
    monkeypatch.setattr(
        "app.teams.expert_chat",
        lambda p, m, session_id=None: ("", None),
    )

    # Moving mock: after 4 creates the board has active tasks (real behavior).
    def build(title, **kw):
        calls["kanban_create"] += 1
        return f"t_{calls['kanban_create'] - 1}"

    monkeypatch.setattr("app.teams.kanban_create", build)

    def kanban_list():
        if calls["kanban_create"] >= 4:
            return [{"id": "t_0", "status": "ready", "assignee": "researcher-b", "parents": []}]
        return []

    monkeypatch.setattr("app.teams.kanban_list", kanban_list)

    results = [None, None]

    def run(i):
        results[i] = teams.invoke_team("agent", "并发调研")

    t1 = threading.Thread(target=run, args=(0,))
    t2 = threading.Thread(target=run, args=(1,))
    t1.start(); t2.start(); t1.join(); t2.join()
    assert calls["kanban_create"] <= 4, "must not build two full trees"