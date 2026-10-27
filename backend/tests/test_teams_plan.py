"""Tests for planner/executor decoupled team orchestration."""

import json

import pytest

from app import teams
from app.hermes_client import HermesError


def _fake_create(created):
    def _create(title, **kw):
        created.append((title, kw))
        return f"t_{len(created) - 1}"

    return _create


def _stub_llm(monkeypatch, output):
    monkeypatch.setattr("app.teams.run_hermes", lambda *a, **k: output)
    # Keep team-member resolution off the real Hermes CLI.
    monkeypatch.setattr(
        "app.teams._registered_expert_ids",
        lambda: ["researcher-a", "researcher-b", "reviewer", "writer"],
    )


def test_invoke_uses_orchestrator_plan(monkeypatch):
    """A valid JSON plan from the orchestrator drives task creation."""
    created = []
    monkeypatch.setattr("app.teams.kanban_create", _fake_create(created))
    _stub_llm(
        monkeypatch,
        json.dumps(
            {
                "tasks": [
                    {
                        "title": "调研框架A",
                        "assignee": "researcher-a",
                        "parents": [],
                        "body": "技术调研",
                    },
                    {
                        "title": "整合报告",
                        "assignee": "writer",
                        "parents": [0],
                        "body": "最终报告",
                        "final": True,
                    },
                ]
            },
            ensure_ascii=False,
        ),
    )
    result = teams.invoke_team("research", "调研")
    assert result["orchestrator_task_id"] == "t_1"
    assert [t[0] for t in created] == ["调研框架A", "整合报告"]
    # Writer task created second, depends on first.
    assert created[1][1]["parent_ids"] == ["t_0"]
    assert created[1][1]["assignee"] == "writer"


def test_invoke_plan_with_warning_prefix(monkeypatch):
    """LLM output may include prose before the JSON code block."""
    created = []
    monkeypatch.setattr("app.teams.kanban_create", _fake_create(created))
    _stub_llm(
        monkeypatch,
        '好的，我拆解如下：\n```json\n{"tasks": ['
        '{"title": "调研", "assignee": "researcher-a", "parents": []},'
        '{"title": "报告", "assignee": "writer", "parents": [0], "final": true}'
        "]}\n```",
    )
    result = teams.invoke_team("research", "调研")
    assert result["orchestrator_task_id"] == "t_1"
    assert len(created) == 2


def test_invoke_falls_back_when_plan_unparseable(monkeypatch):
    """Garbage LLM output falls back to the default task tree."""
    created = []
    monkeypatch.setattr("app.teams.kanban_create", _fake_create(created))
    _stub_llm(monkeypatch, "抱歉，我无法处理这个需求。")
    result = teams.invoke_team("research", "调研")
    # Default template: 4 tasks (tech, case, review, final).
    assert len(created) == 4
    assert result["orchestrator_task_id"] == "t_3"
    assert created[3][1]["assignee"] == "writer"


def test_invoke_falls_back_when_assignee_invalid(monkeypatch):
    """A plan referencing an unknown member falls back to default tree."""
    created = []
    monkeypatch.setattr("app.teams.kanban_create", _fake_create(created))
    _stub_llm(
        monkeypatch,
        json.dumps(
            {
                "tasks": [
                    {
                        "title": "调研",
                        "assignee": "unknown-expert",  # 不在 members
                        "parents": [],
                    }
                ]
            }
        ),
    )
    result = teams.invoke_team("research", "调研")
    assert len(created) == 4  # fell back to default
    assert result["orchestrator_task_id"] == "t_3"


def test_invoke_falls_back_when_orchestrator_fails(monkeypatch):
    """Hermes CLI failure during the orchestrator call still produces a tree."""
    created = []
    monkeypatch.setattr("app.teams.kanban_create", _fake_create(created))
    monkeypatch.setattr(
        "app.teams._registered_expert_ids",
        lambda: ["researcher-a", "researcher-b", "reviewer", "writer"],
    )

    def fail_run(*a, **k):
        raise HermesError("orchestrator crashed")

    monkeypatch.setattr("app.teams.run_hermes", fail_run)
    result = teams.invoke_team("research", "调研")
    assert len(created) == 4
    assert result["orchestrator_task_id"] == "t_3"