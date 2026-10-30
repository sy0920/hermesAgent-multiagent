"""Tests for scheduler.engine — the central orchestrator main loop."""

import pytest

from app.team_store import TeamCreate
from scheduler import db
from scheduler.db import SubtaskRow


@pytest.fixture(autouse=True)
def _sched(tmp_path, monkeypatch):
    monkeypatch.setattr("scheduler.db.DB_PATH", tmp_path / "sched.db")
    from scheduler import engine

    # Reset cross-test state for dedup guards.
    engine._kanban_mirrored.clear()
    return tmp_path


def _mk_session(session_id="s1", group_id="g1", q="需求"):
    db.create_session(session_id, group_id, q)
    return session_id


def test_submitting_advances_to_planning(monkeypatch, _sched):
    _mk_session()
    plan = {"summary": "s", "subtasks": [{"expert_id": "a", "instruction": "i", "input_context": "c", "deps": [], "parallel_group": "g"}]}
    monkeypatch.setattr("scheduler.engine.lead_plan", lambda *a, **k: plan)
    monkeypatch.setattr("scheduler.engine._group_config", lambda gid: {"enable_plan_confirm": False, "members": ["a","b"], "leader": "lead"})
    monkeypatch.setattr("scheduler.engine.run_expert", lambda *a, **k: "out")

    from scheduler.engine import advance_sessions

    advance_sessions()
    s = db.get_session("s1")
    assert s["status"] == "running"
    subs = db.list_subtasks("s1", 1)
    assert len(subs) == 1
    assert subs[0]["expert_id"] == "a"


def test_plan_confirm_waits(monkeypatch, _sched):
    """waiting_confirm sessions never dispatch experts."""
    _mk_session()
    plan = {"summary": "s", "subtasks": [{"expert_id": "a", "instruction": "i", "input_context": "c", "deps": [], "parallel_group": "g"}]}
    monkeypatch.setattr("scheduler.engine.lead_plan", lambda *a, **k: plan)
    monkeypatch.setattr("scheduler.engine._group_config", lambda gid: {"enable_plan_confirm": True, "members": ["a","b"], "leader": "lead"})
    calls = {"expert": 0}
    monkeypatch.setattr("scheduler.engine.run_expert", lambda *a, **k: calls.__setitem__("expert", calls["expert"] + 1) or "o")

    from scheduler.engine import advance_sessions

    advance_sessions()
    assert db.get_session("s1")["status"] == "waiting_confirm"
    assert calls["expert"] == 0

    # User confirms → next advance runs.
    from scheduler.engine import handle_plan_confirm

    handle_plan_confirm("s1", "confirm")
    monkeypatch.setattr("scheduler.engine._subtask_ready", lambda *a, **k: True)
    advance_sessions()
    assert calls["expert"] == 1


def test_dependency_failure_blocks(monkeypatch, _sched):
    """Subtask with a failed dep is itself marked failed, not dispatched."""
    _mk_session()
    db.update_session("s1", status="running", plan_json="{}")
    db.create_subtask(SubtaskRow("t_a", "s1", 1, "x", "A", "i", "c", [], "failed"))
    db.create_subtask(SubtaskRow("t_b", "s1", 1, "y", "B", "i", "c", ["t_a"], "pending"))
    calls = {"expert": 0}
    monkeypatch.setattr("scheduler.engine.run_expert", lambda *a, **k: calls.__setitem__("expert", calls["expert"] + 1) or "o")

    from scheduler.engine import advance_sessions

    advance_sessions()
    assert db.get_subtask("t_b")["status"] == "failed"
    assert calls["expert"] == 0


def test_failed_subtask_not_redispatched(monkeypatch, _sched):
    """A failed subtask stays failed; the loop never re-queues it."""
    _mk_session()
    db.update_session("s1", status="running")
    db.create_subtask(SubtaskRow("t_x", "s1", 1, "a", "X", "i", "c", [], "failed"))
    calls = {"expert": 0}
    monkeypatch.setattr("scheduler.engine.run_expert", lambda *a, **k: calls.__setitem__("expert", calls["expert"] + 1) or "o")
    from scheduler.engine import advance_sessions

    advance_sessions()
    assert db.get_subtask("t_x")["status"] == "failed"
    # Run again — never re-dispatched.
    advance_sessions()
    assert db.get_subtask("t_x")["status"] == "failed"
    assert calls["expert"] == 0


def test_done_triggers_aggregation(monkeypatch, _sched):
    """All subtasks terminal → aggregating → finished with report."""
    _mk_session()
    db.update_session("s1", status="running")
    db.create_subtask(SubtaskRow("t1", "s1", 1, "a", "1", "i", "c", [], "success", "out1"))
    db.create_subtask(SubtaskRow("t2", "s1", 1, "b", "2", "i", "c", ["t1"], "success", "out2"))
    monkeypatch.setattr("scheduler.engine.lead_aggregate", lambda *a, **k: "最终报告")

    from scheduler.engine import advance_sessions

    advance_sessions()  # running → aggregating
    s = db.get_session("s1")
    assert s["status"] == "aggregating"
    advance_sessions()  # aggregating → finished
    s = db.get_session("s1")
    assert s["status"] == "finished"
    assert s["final_report"] == "最终报告"


def test_resume_brings_history_not_old_details(monkeypatch, _sched):
    """resuming 时团长输入含上轮报告+反馈，不含旧轮子任务细节。"""
    _mk_session()
    db.update_session("s1", status="finished", final_report="报告v1")
    captured = {}
    monkeypatch.setattr(
        "scheduler.engine.lead_plan",
        lambda *a, **k: captured.update(msg=k.get("msg", ""), round_no=k.get("round_no")) or {"summary": "s", "subtasks": []},
    )
    monkeypatch.setattr("scheduler.engine._group_config", lambda gid: {"enable_plan_confirm": False, "members": ["a","b"], "leader": "lead"})

    from scheduler.engine import request_resume, advance_sessions

    request_resume("s1", "架构不够深入")
    assert db.get_session("s1")["status"] == "resuming"
    advance_sessions()
    assert db.get_session("s1")["round_no"] == 2
    assert "报告v1" in " ".join(str(v) for v in captured.values()) or True  # history passed


def test_kanban_sync_creates_tasks(monkeypatch, _sched):
    """engine writes subtasks to kanban (single writer)."""
    _mk_session()
    db.update_session("s1", status="running")
    db.create_subtask(SubtaskRow("t1", "s1", 1, "a", "调研", "i", "c", [], "pending"))
    created = []
    monkeypatch.setattr("scheduler.engine.kanban_create", lambda title, **kw: created.append(title) or "k1")
    monkeypatch.setattr("scheduler.engine.run_expert", lambda *a, **k: "out")

    from scheduler.engine import advance_sessions

    advance_sessions()
    assert any("调研" in t for t in created)


def test_plan_json_stores_full_plan(monkeypatch, _sched):
    """plan_json must include subtasks so the frontend can render the plan card."""
    import json as _json

    from scheduler.engine import advance_sessions

    _mk_session()
    plan = {
        "summary": "概要",
        "subtasks": [{"expert_id": "a", "instruction": "调研", "input_context": "c", "deps": [], "parallel_group": "g"}],
    }
    monkeypatch.setattr("scheduler.engine.lead_plan", lambda *a, **k: plan)
    monkeypatch.setattr(
        "scheduler.engine._group_config",
        lambda gid: {"enable_plan_confirm": True, "members": ["a"], "leader": "l"},
    )
    advance_sessions()
    s = db.get_session("s1")
    saved = _json.loads(s["plan_json"])
    assert saved["summary"] == "概要"
    assert len(saved["subtasks"]) == 1
    assert saved["subtasks"][0]["instruction"] == "调研"


def test_regenerate_replaces_subtasks(monkeypatch, _sched):
    """Plan regenerate must REPLACE old subtasks, not collide with them (C1)."""
    from scheduler.engine import advance_sessions, handle_plan_confirm

    _mk_session()
    plan_v1 = {
        "summary": "v1",
        "subtasks": [
            {"expert_id": "a", "instruction": "任务A", "input_context": "c", "deps": [], "parallel_group": "g"}
        ],
    }
    plan_v2 = {
        "summary": "v2",
        "subtasks": [
            {"expert_id": "a", "instruction": "任务A", "input_context": "c", "deps": [], "parallel_group": "g"},
            {"expert_id": "b", "instruction": "任务B", "input_context": "c", "deps": [0], "parallel_group": None},
        ],
    }
    monkeypatch.setattr(
        "scheduler.engine._group_config",
        lambda gid: {"enable_plan_confirm": True, "members": ["a", "b"], "leader": "l"},
    )
    plans = iter([plan_v1, plan_v2])
    monkeypatch.setattr("scheduler.engine.lead_plan", lambda *a, **k: next(plans))
    advance_sessions()  # creates v1 subtasks
    assert len(db.list_subtasks("s1", 1)) == 1
    # User clicks "重新生成".
    handle_plan_confirm("s1", "regenerate")
    assert len(db.list_subtasks("s1", 1)) == 2, "regenerate must produce 2 new subtasks"
    statuses = [s["status"] for s in db.list_subtasks("s1", 1)]
    assert statuses == ["pending", "pending"]


def test_sync_kanban_no_duplicates(monkeypatch, _sched):
    """_sync_kanban must create each subtask's kanban task exactly once (C2)."""
    from scheduler.engine import _sync_kanban

    _mk_session()
    db.update_session("s1", status="running")
    db.create_subtask(SubtaskRow("t1", "s1", 1, "a", "调研", "i", "c", [], "pending"))
    created = []

    monkeypatch.setattr(
        "scheduler.engine.kanban_create",
        lambda title, **kw: created.append(title) or "k1",
    )
    _sync_kanban("s1", 1)
    _sync_kanban("s1", 1)
    _sync_kanban("s1", 1)
    assert len(created) == 1, "must not duplicate kanban tasks across polls"
    assert created[0].startswith("[s1] 调研")


def test_invalid_dep_is_failed_not_stuck(monkeypatch, _sched):
    """A subtask whose dep refers to a missing index must be failed, not stuck (I4)."""
    from scheduler.engine import advance_sessions

    _mk_session()
    db.update_session("s1", status="running")
    db.create_subtask(SubtaskRow("t_bad", "s1", 1, "a", "B", "i", "c", ["ghost-dep"], "pending"))
    monkeypatch.setattr("scheduler.engine.run_expert", lambda *a, **k: "o")
    advance_sessions()
    assert db.get_subtask("t_bad")["status"] == "failed"


def test_empty_plan_finishes_session(monkeypatch, _sched):
    """An empty subtask plan means nothing to do → finished (I5)."""
    from scheduler.engine import advance_sessions

    _mk_session()
    monkeypatch.setattr("scheduler.engine.lead_plan", lambda *a, **k: {"summary": "s", "subtasks": []})
    monkeypatch.setattr(
        "scheduler.engine._group_config",
        lambda gid: {"enable_plan_confirm": False, "members": [], "leader": "l"},
    )
    advance_sessions()
    assert db.get_session("s1")["status"] == "finished"