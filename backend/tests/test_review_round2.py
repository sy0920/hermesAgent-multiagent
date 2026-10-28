"""Tests for the cross-context handoff and parallel auto-dispatch fixes.

Problem 2: invoke_team should auto-dispatch ready tasks in parallel and
            the chain should reach 'final' once all members complete.
Problem 3: run_task must inject parent-task summaries into the worker's
            context so downstream members see upstream outputs.
Problem 4: create_expert must persist model config on the profile, and
            status should reflect the real gateway state rather than a
            hardcoded 'parked'.
"""

import asyncio
import json

import pytest

from app import experts, kanban, teams
from app.hermes_client import HermesError
from app.schemas import ExpertCreate
from app.team_store import TeamCreate
from fastapi import BackgroundTasks, HTTPException


@pytest.fixture(autouse=True)
def _temp_team_store(tmp_path, monkeypatch):
    """Provide a 'research' team for team-scoped tests."""
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
    teams._invoke_windows.clear()


# ---------------------------------------------------------------------------
# Problem 2: parallel auto-dispatch + final aggregation
# ---------------------------------------------------------------------------


def test_invoke_auto_dispatches_workers_in_parallel(monkeypatch):
    """advance_once dispatches all ready root tasks in parallel."""
    created = []
    monkeypatch.setattr(
        "app.teams.expert_chat",
        lambda p, m, session_id=None: ("", None),  # planner silent → fallback
    )
    monkeypatch.setattr(
        "app.teams.kanban_create",
        lambda title, **kw: created.append((title, kw)) or f"t_{len(created) - 1}",
    )

    # kanban_list returns the created root tasks as 'ready'.
    monkeypatch.setattr(
        "app.teams.kanban_list",
        lambda: [
            {"id": "t_0", "status": "ready", "assignee": "researcher-a", "parents": []},
            {"id": "t_1", "status": "ready", "assignee": "researcher-b", "parents": []},
            {"id": "t_2", "status": "todo", "assignee": "reviewer", "parents": ["t_0", "t_1"]},
            {"id": "t_3", "status": "todo", "assignee": "writer", "parents": ["t_2"]},
        ],
    )

    dispatched = []
    monkeypatch.setattr(
        "app.teams.execute_kanban_task",
        lambda profile, task_id, **kw: dispatched.append((profile, task_id)) or "",
    )

    # advance_once is the dispatcher; it must fire both ready roots.
    teams._recent_dispatch.clear()
    teams.advance_once()
    profiles = [d[0] for d in dispatched]
    assert "researcher-a" in profiles
    assert "researcher-b" in profiles


def test_team_final_aggregates_from_done_writer(monkeypatch):
    """team_final should read the writer task's metadata['final'] when done."""
    monkeypatch.setattr(
        "app.teams.kanban_list",
        lambda: [
            {"id": "t_w", "title": "综合报告", "status": "done", "assignee": "writer", "parents": ["t_r"]},
        ],
    )
    monkeypatch.setattr(
        "app.teams.kanban_show",
        lambda i: {"id": i, "metadata": {"final": "# 最终报告"}},
    )
    result = teams.team_final("research")
    assert result.report == "# 最终报告"


# ---------------------------------------------------------------------------
# Problem 3: parent-summary injection
# ---------------------------------------------------------------------------


def test_run_task_injects_parent_summary_into_body(monkeypatch):
    """When a task has parents, the worker prompt must include parent summaries."""
    monkeypatch.setattr(
        "app.kanban.kanban_show",
        lambda i: {
            "id": i,
            "title": "审核报告",
            "assignee": "reviewer",
            "parents": ["t_tech"],
            "body": "原始body",
            "summary": None,
        },
    )
    parent_summary = "调研结论：AutoGen 用 actor 模型"
    monkeypatch.setattr(
        "app.kanban.kanban_show",
        lambda i: (
            {"id": "t_tech", "title": "技术调研", "summary": parent_summary, "metadata": {}}
            if i == "t_tech"
            else {
                "id": i,
                "title": "审核报告",
                "assignee": "reviewer",
                "parents": ["t_tech"],
                "body": "原始body",
            }
        ),
    )
    captured = {}
    monkeypatch.setattr(
        "app.kanban.execute_kanban_task",
        lambda profile, task_id, extra_context=None: captured.update(
            profile=profile, task_id=task_id, extra_context=extra_context
        )
        or "",
    )
    tasks = BackgroundTasks()
    kanban.run_task("t_review", background_tasks=tasks)
    # Execute the scheduled background task.
    item = tasks.tasks[0]
    item.func(*item.args, **item.kwargs)
    assert captured["profile"] == "reviewer"
    assert parent_summary in (captured["extra_context"] or "")


# ---------------------------------------------------------------------------
# Problem 4: model config + status
# ---------------------------------------------------------------------------


def test_create_expert_persists_model_config(monkeypatch, tmp_path):
    fake_home = tmp_path / "home"
    profiles = fake_home / ".hermes" / "profiles"
    monkeypatch.setattr("app.experts.Path.home", staticmethod(lambda: fake_home))
    monkeypatch.setattr("app.experts._profile_home", lambda: profiles)
    monkeypatch.setattr("app.experts.profile_list", lambda: [])
    monkeypatch.setattr("app.experts.profile_create", lambda n: None)
    monkeypatch.setattr(
        "app.experts.profile_soul_path",
        lambda n: str(profiles / n / "SOUL.md"),
    )
    calls = []
    monkeypatch.setattr("app.experts.run_hermes", lambda *a, **k: calls.append(a) or "")

    payload = ExpertCreate(
        display_name="sql-doctor",
        persona="10年DBA",
        expertise="SQL调优",
        prompt="输出问题-根因-建议",
        model="deepseek-reasoner",
    )
    experts.create_expert(payload)
    # At least one run_hermes call should configure the model.
    model_calls = [c for c in calls if "model" in " ".join(str(x) for x in c)]
    assert len(model_calls) >= 1, f"model config not called; calls={calls}"


def test_read_expert_status_from_gateway(monkeypatch, tmp_path):
    fake_home = tmp_path / "home"
    profiles = fake_home / ".hermes" / "profiles"
    (profiles / "researcher-a").mkdir(parents=True)
    (profiles / "researcher-a" / "SOUL.md").write_text(
        "# Persona\n资深研究员\n\n# Expertise\n技术\n\n# Prompt\n列表\n", encoding="utf-8"
    )
    monkeypatch.setattr("app.experts.Path.home", staticmethod(lambda: fake_home))
    monkeypatch.setattr("app.experts._profile_home", lambda: profiles)
    monkeypatch.setattr("app.experts.profile_list", lambda: ["researcher-a"])
    monkeypatch.setattr(
        "app.experts.profile_soul_path",
        lambda n: str(profiles / n / "SOUL.md"),
    )
    # Simulate `hermes profile list` output with a 'running' gateway status.
    monkeypatch.setattr(
        "app.experts.run_hermes",
        lambda *a, **k: "researcher-a  running  deepseek-chat\n",
    )
    expert = experts._read_expert("researcher-a")
    assert expert.status == "running"