"""Tests for memory-based invoke idempotency (no kanban parsing dependency)."""

import pytest

from app import teams
from app.team_store import TeamCreate

# Ensure a fresh idempotency window between tests.
teams._invoke_windows.clear()


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
    yield
    teams._invoke_windows.clear()


def _monkey_build(monkeypatch):
    calls = {"kanban_create": 0}
    monkeypatch.setattr(
        "app.teams.expert_chat",
        lambda p, m, session_id=None: ("", None),
    )
    monkeypatch.setattr(
        "app.teams.kanban_create",
        lambda title, **kw: calls.__setitem__("kanban_create", calls["kanban_create"] + 1) or f"t_{calls['kanban_create'] - 1}",
    )
    # kanban_list always returns [] (as if tasks invisible) → old
    # active-tasks-based idempotency would fail here; memory window must hold.
    monkeypatch.setattr("app.teams.kanban_list", lambda: [])
    return calls


def test_memory_window_blocks_second_invoke(monkeypatch):
    """Within the window, a second invoke reuses the first result."""
    calls = _monkey_build(monkeypatch)
    first = teams.invoke_team("agent", "调研")
    n_after_first = calls["kanban_create"]
    assert n_after_first == 4

    second = teams.invoke_team("agent", "调研再来一次")
    assert calls["kanban_create"] == n_after_first, "window must block re-invoke"
    assert second["orchestrator_task_id"] == first["orchestrator_task_id"]


def test_memory_window_expires(monkeypatch):
    """After the window expires, a new invoke builds a fresh tree."""
    calls = _monkey_build(monkeypatch)
    teams.invoke_team("agent", "调研")
    # Force window expiry by back-dating the recorded timestamp.
    teams._invoke_windows["agent"] = (
        teams._invoke_windows["agent"][0],
        teams._invoke_windows["agent"][1] - teams.INVOKE_WINDOW_SECONDS - 1,
    )
    result = teams.invoke_team("agent", "新的调研")
    assert calls["kanban_create"] == 8
    assert result["orchestrator_task_id"] == "t_7"