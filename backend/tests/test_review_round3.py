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

    class FakeGateway:
        def poll(self):
            return None  # gateway "running"

        def __init__(self, *a, **k):
            pass

    def fake_run(args, **kwargs):
        captured["args"] = args
        captured["env"] = kwargs.get("env") or {}
        return FakeProc()

    monkeypatch.setattr("app.hermes_client.subprocess.run", fake_run)
    monkeypatch.setattr("app.hermes_client.subprocess.Popen", FakeGateway)
    monkeypatch.setattr("app.hermes_client.time.sleep", lambda s: None)
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
    root = teams._build_default_tree("调研需求", ["sql", "reviewer", "writer"], leader=None)
    assert captured["workspace"], "task must use a persistent dir workspace"
    assert captured["workspace"].startswith("dir:"), captured["workspace"]


def test_build_default_tree_assignees_from_members(monkeypatch):
    """I2: fallback tree assigns only with the team's own members."""
    created = []
    monkeypatch.setattr(
        "app.teams.kanban_create",
        lambda title, **kw: created.append(kw.get("assignee")) or "t_x",
    )
    teams._build_default_tree("调研", ["sql", "reviewer", "writer"], leader="writer")
    assignees = set(a for a in created if a)
    assert assignees <= {"sql", "reviewer"}
    assert "writer" not in assignees, "leader must not execute tasks"


def test_build_default_tree_without_leader(monkeypatch):
    """No leader provided behaves like before (all members eligible)."""
    created = []
    monkeypatch.setattr(
        "app.teams.kanban_create",
        lambda title, **kw: created.append(kw.get("assignee")) or "t_x",
    )
    teams._build_default_tree("调研", ["a", "b", "c"], leader=None)
    assert "a" in created


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
        "app.teams._dispatch_worker_safe",
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
        "app.teams._dispatch_worker_safe",
        lambda profile, task_id, **kw: dispatched.append((profile, task_id)) or "",
    )
    teams.advance_once()
    assert dispatched == []


def test_advance_loop_tracks_recent_dispatch(monkeypatch):
    """A task already dispatched once is never re-dispatched (token safety)."""
    teams._dispatched_once.clear()
    teams._dispatched_once.add("t_child")
    rows = [
        {"id": "t_child", "status": "ready", "assignee": "writer", "parents": []},
    ]
    monkeypatch.setattr("app.teams.kanban_list", lambda: rows)
    dispatched = []
    monkeypatch.setattr(
        "app.teams._dispatch_worker_safe",
        lambda profile, task_id, **kw: dispatched.append((profile, task_id)) or "",
    )
    teams.advance_once()
    assert dispatched == []
    teams._dispatched_once.clear()


def test_advance_loop_does_not_redispatch_on_failure(monkeypatch):
    """A failed worker must NOT be auto-re-queued (the runaway loop)."""
    teams._dispatched_once.clear()
    rows = [
        {"id": "t_x", "status": "ready", "assignee": "researcher-a", "parents": []},
    ]
    monkeypatch.setattr("app.teams.kanban_list", lambda: rows)
    attempts = []

    def fail_then_track(profile, task_id, **kw):
        attempts.append(task_id)
        raise HermesError("worker crashed")

    monkeypatch.setattr("app.teams._dispatch_worker_safe", fail_then_track)
    teams.advance_once()
    # Simulate the next loop tick: task still marked ready in Hermes.
    attempts.clear()
    teams.advance_once()
    assert attempts == [], "must not re-dispatch a task that already ran"
    teams._dispatched_once.clear()


def test_build_from_plan_deduplicates_titles(monkeypatch):
    """A duplicated title in the planner's plan creates only one task."""
    created = []
    monkeypatch.setattr(
        "app.teams.kanban_create",
        lambda title, **kw: created.append(title) or f"t_{len(created) - 1}",
    )
    plan = {
        "tasks": [
            {"title": "调研 AutoGen 架构", "assignee": "researcher-a", "parents": []},
            {"title": "调研 AutoGen 架构", "assignee": "researcher-a", "parents": []},  # dup
            {"title": "汇总报告", "assignee": "writer", "parents": [0], "final": True},
        ]
    }
    final = teams._build_from_plan(plan, "调研 AutoGen")
    assert created.count("调研 AutoGen 架构") == 1
    assert len(created) == 2
    assert final == "t_1"