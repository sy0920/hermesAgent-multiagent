"""Tests for the kanban bridge routes."""

import pytest

from app import kanban
from app.hermes_client import HermesError


def test_task_children_derived_from_parents(monkeypatch):
    rows = [
        {"id": "t_a", "title": "a", "status": "done", "assignee": "r", "parents": []},
        {
            "id": "t_b",
            "title": "b",
            "status": "todo",
            "assignee": "w",
            "parents": ["t_a"],
        },
    ]
    monkeypatch.setattr("app.kanban.kanban_list", lambda: rows)
    result = kanban.list_tasks()
    ta = next(x for x in result if x.id == "t_a")
    assert ta.children == ["t_b"]


def test_list_tasks_normalizes_status(monkeypatch):
    rows = [
        {
            "id": "t_1",
            "title": "x",
            "status": "doing",  # Hermes may report doing; frontend expects doing
            "assignee": "a",
            "parents": [],
        }
    ]
    monkeypatch.setattr("app.kanban.kanban_list", lambda: rows)
    result = kanban.list_tasks()
    assert result[0].status == "doing"


def test_run_task_returns_started(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "app.kanban.kanban_show",
        lambda i: {"id": i, "assignee": "researcher-a"},
    )
    monkeypatch.setattr(
        "app.kanban.execute_kanban_task",
        lambda p, t: captured.update(profile=p, task=t) or "done",
    )
    result = kanban.run_task("t_1")
    assert result.status == "started"
    assert result.run_id == "t_1"
    assert captured == {"profile": "researcher-a", "task": "t_1"}


def test_run_unknown_task_404(monkeypatch):
    def fail_show(i):
        raise HermesError("no matching task")

    monkeypatch.setattr("app.kanban.kanban_show", fail_show)
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        kanban.run_task("t_nope")
    assert exc_info.value.status_code == 404


def test_task_detail_builds_runs_and_metadata(monkeypatch):
    monkeypatch.setattr(
        "app.kanban.kanban_show",
        lambda i: {
            "id": i,
            "title": "专题",
            "status": "done",
            "assignee": "writer",
            "parents": ["t_r"],
            "body": "整合报告",
            "summary": "完成了",
            "metadata": {"final": "# 报告"},
            "runs": [{"run_id": 1, "outcome": "completed"}],
        },
    )
    detail = kanban.task_detail("t_w")
    assert detail.body == "整合报告"
    assert detail.summary == "完成了"
    assert detail.metadata["final"] == "# 报告"
    assert len(detail.runs) == 1