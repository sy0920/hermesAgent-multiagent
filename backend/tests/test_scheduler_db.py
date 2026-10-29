"""Tests for scheduler.db (SQLite session/subtask ledger)."""

import pytest

from scheduler.db import (
    SubtaskRow,
    create_session,
    create_subtask,
    get_session,
    get_subtask,
    list_sessions,
    list_subtasks,
    update_session,
    update_subtask,
)


@pytest.fixture
def sched_home(tmp_path, monkeypatch):
    monkeypatch.setattr("scheduler.db.DB_PATH", tmp_path / "sched.db")
    return tmp_path


def test_session_roundtrip(sched_home):
    create_session("s1", "g1", "调研 AutoGen")
    s = get_session("s1")
    assert s["group_id"] == "g1"
    assert s["status"] == "submitting"
    assert s["round_no"] == 1


def test_update_session(sched_home):
    create_session("s1", "g1", "q")
    update_session("s1", status="running", plan_json="{}")
    s = get_session("s1")
    assert s["status"] == "running"
    assert s["plan_json"] == "{}"


def test_session_status_filter(sched_home):
    create_session("s1", "g1", "q")
    create_session("s2", "g1", "q")
    update_session("s1", status="finished")
    assert {s["session_id"] for s in list_sessions(status="finished")} == {"s1"}
    assert len(list_sessions()) == 2


def test_subtask_roundtrip_with_deps(sched_home):
    create_session("s1", "g1", "q")
    create_subtask(SubtaskRow("t1", "s1", 1, "expert-a", "调研", "读文档", "ctx", ["t0"], "pending"))
    r = get_subtask("t1")
    assert r["deps"] == ["t0"]
    assert r["status"] == "pending"
    update_subtask("t1", status="success", output="结果")
    assert get_subtask("t1")["status"] == "success"
    assert get_subtask("t1")["output"] == "结果"


def test_list_subtasks_by_round(sched_home):
    create_session("s1", "g1", "q")
    create_subtask(SubtaskRow("t1", "s1", 1, "a", "x", "i", "c", [], "pending"))
    create_subtask(SubtaskRow("t2", "s1", 2, "b", "y", "i", "c", [], "pending"))
    assert {t["subtask_id"] for t in list_subtasks("s1", 1)} == {"t1"}
    assert {t["subtask_id"] for t in list_subtasks("s1", 2)} == {"t2"}


def test_update_missing_returns_none(sched_home):
    assert update_session("nope", status="x") is None