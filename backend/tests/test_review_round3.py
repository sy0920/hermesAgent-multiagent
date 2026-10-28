"""Tests for the closure-layer fixes.

A. execute_kanban_task instructs the worker to complete via kanban tools
   and write metadata.final (so team_final can aggregate).
B. Team membership is dynamic (from the expert registry), not hardcoded.
C. Task creation persists outputs to a shared workspace directory.
D. A background advance loop auto-dispatches newly-ready tasks (incl. ones
   unblocked when their parents complete) and records the final report.
"""

import json
import threading
import time

import pytest

from app import teams
from app.hermes_client import HermesError, execute_kanban_task, run_hermes


# ---------------------------------------------------------------------------
# A. worker completion contract
# ---------------------------------------------------------------------------


def test_execute_kanban_task_includes_completion_contract(monkeypatch):
    captured = {}
    captured["args"] = None

    class FakeProc:
        returncode = 0
        stdout = "done"
        stderr = ""

    def fake_run(args, **kwargs):
        captured["args"] = args
        captured["env"] = kwargs.get("env") or {}
        return FakeProc()

    monkeypatch.setattr("app.hermes_client.subprocess.run", fake_run)
    execute_kanban_task("writer", "t_9", extra_context="上游摘要")
    joined = " ".join(str(x) for x in captured["args"])
    assert "kanban_complete" in joined
    assert "metadata" in joined
    assert "final" in joined
    # The worker must be told it is the kanban task owner.
    assert "t_9" in joined
    # Upstream context rides along.
    assert "上游摘要" in joined


# ---------------------------------------------------------------------------
# B. dynamic team membership
# ---------------------------------------------------------------------------


def test_team_members_from_store(tmp_path, monkeypatch):
    """Members come from the persisted team (leader + chosen members)."""
    from app.team_store import TeamCreate

    fake_home = tmp_path / "home"
    (fake_home / ".hermes").mkdir(parents=True)
    p = fake_home / ".hermes" / "teams.json"
    monkeypatch.setattr("app.team_store.TEAMS_PATH", p)
    teams._team_store().create(
        TeamCreate(
            display_name="SQL团",
            leader="sql",
            members=["sql", "reviewer", "writer"],
        )
    )
    team = teams._get_team("sql")
    assert team.leader == "sql"
    assert "sql" in team.members and "writer" in team.members


# ---------------------------------------------------------------------------
# C. persistent workspace on task creation
# ---------------------------------------------------------------------------


def test_build_default_tree_uses_shared_workspace(monkeypatch):
    captured = {}

    def fake_create(title, **kw):
        captured["workspace"] = kw.get("workspace")
        captured["parent_ids"] = kw.get("parent_ids")
        return f"t_{len(captured)}"

    monkeypatch.setattr("app.teams.kanban_create", fake_create)
    root = teams._build_default_tree("调研需求", ["sql", "reviewer", "writer"])
    assert captured["workspace"], "task must use a persistent dir workspace"
    assert captured["workspace"].startswith("dir:"), captured["workspace"]


def test_build_default_tree_assignees_from_members(monkeypatch):
    """I2: fallback tree assigns only with the team's own members."""
    created = []
    monkeypatch.setattr(
        "app.teams.kanban_create",
        lambda title, **kw: created.append(kw.get("assignee")) or "t_x",
    )
    teams._build_default_tree("调研", ["sql", "reviewer", "writer"])
    assignees = set(a for a in created if a)
    assert assignees <= {"sql", "reviewer", "writer"}


# ---------------------------------------------------------------------------
# D. advance loop: unblocked tasks get auto-dispatched
# ---------------------------------------------------------------------------


def _fake_rows(*task_dicts):
    return [dict(d) for d in task_dicts]


def test_advance_loop_dispatches_unblocked_ready(monkeypatch):
    """A task that turns 'ready' because its parents are done is dispatched."""
    state = {
        "seen": {"t_root": "running"},
        "dispatched": [],
    }

    rows = [
        {"id": "t_root", "status": "done", "assignee": "researcher-a", "parents": []},
        {"id": "t_child", "status": "ready", "assignee": "reviewer", "parents": ["t_root"]},
    ]
    monkeypatch.setattr("app.teams.kanban_list", lambda: rows)
    dispatched = []
    monkeypatch.setattr(
        "app.teams.execute_kanban_task",
        lambda profile, task_id, **kw: dispatched.append((profile, task_id)) or "",
    )

    teams.advance_once()
    assert ("reviewer", "t_child") in dispatched


def test_advance_loop_skips_non_ready(monkeypatch):
    """Tasks still blocked or already running are not dispatched again."""
    rows = [
        {"id": "t_a", "status": "blocked", "assignee": "x", "parents": ["t_z"]},
        {"id": "t_b", "status": "running", "assignee": "y", "parents": []},
    ]
    monkeypatch.setattr("app.teams.kanban_list", lambda: rows)
    dispatched = []
    monkeypatch.setattr(
        "app.teams.execute_kanban_task",
        lambda profile, task_id, **kw: dispatched.append((profile, task_id)) or "",
    )
    teams.advance_once()
    assert dispatched == []


def test_advance_loop_tracks_recent_dispatch(monkeypatch):
    """A task already dispatched recently is not re-dispatched."""
    teams._recent_dispatch.clear()
    teams._recent_dispatch["t_child"] = time.time()
    rows = [
        {"id": "t_child", "status": "ready", "assignee": "writer", "parents": []},
    ]
    monkeypatch.setattr("app.teams.kanban_list", lambda: rows)
    dispatched = []
    monkeypatch.setattr(
        "app.teams.execute_kanban_task",
        lambda profile, task_id, **kw: dispatched.append((profile, task_id)) or "",
    )
    teams.advance_once()
    assert dispatched == []
    teams._recent_dispatch.clear()