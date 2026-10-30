"""Tests for scheduler.leader — team-lead plan generation & aggregation."""

import pytest

from scheduler.leader import lead_aggregate, lead_plan


def test_lead_plan_parses_json(monkeypatch):
    monkeypatch.setattr(
        "scheduler.leader.chat_budgeted",
        lambda *a, **k: (
            '{"summary":"s","subtasks":['
            '{"expert_id":"a","instruction":"i","input_context":"c","deps":[],"parallel_group":"g"}]}'
        ),
    )
    plan = lead_plan("team-lead", "需求", "a,b")
    assert plan["summary"] == "s"
    assert plan["subtasks"][0]["expert_id"] == "a"


def test_lead_plan_fence_json(monkeypatch):
    monkeypatch.setattr(
        "scheduler.leader.chat_budgeted",
        lambda *a, **k: '```json\n{"summary":"s","subtasks":[]}\n```',
    )
    plan = lead_plan("team-lead", "需求", "a")
    assert plan["summary"] == "s"


def test_lead_plan_prose_around_json(monkeypatch):
    monkeypatch.setattr(
        "scheduler.leader.chat_budgeted",
        lambda *a, **k: '好的，方案如下：%s 后续按此执行' % '{"summary":"x","subtasks":[]}',
    )
    plan = lead_plan("team-lead", "需求", "a")
    assert plan["summary"] == "x"


def test_lead_plan_invalid_returns_none(monkeypatch):
    monkeypatch.setattr("scheduler.leader.chat_budgeted", lambda *a, **k: "不是JSON")
    assert lead_plan("team-lead", "需求", "a") is None


def test_lead_plan_empty_tasks_returns_dict(monkeypatch):
    monkeypatch.setattr("scheduler.leader.chat_budgeted", lambda *a, **k: '{"summary":"s"}')
    plan = lead_plan("team-lead", "需求", "a")
    assert plan is not None
    assert plan["subtasks"] == []


def test_lead_plan_budget_forwarded(monkeypatch):
    captured = {}

    def fake(profile, msg, *, max_turns, run_budget, toolsets, timeout=None):
        captured.update(profile=profile, mt=max_turns, rb=run_budget, ts=toolsets)
        return '{"summary":"s","subtasks":[]}'

    monkeypatch.setattr("scheduler.leader.chat_budgeted", fake)
    lead_plan("team-lead", "需求", "a,b")
    assert captured["profile"] == "team-lead"
    assert captured["mt"] == 5
    assert captured["rb"] == 60
    assert captured["ts"] == ["file", "skills"]


def test_lead_plan_includes_history_and_round(monkeypatch):
    captured = {}

    def fake(profile, msg, **kw):
        captured["msg"] = msg
        return '{"summary":"s","subtasks":[]}'

    monkeypatch.setattr("scheduler.leader.chat_budgeted", fake)
    lead_plan("t", "需求", "a,b", history="上轮报告", round_no=2)
    assert "上轮报告" in captured["msg"]
    assert "第 2 轮" in captured["msg"]


def test_lead_aggregate_returns_report(monkeypatch):
    monkeypatch.setattr("scheduler.leader.chat_budgeted", lambda *a, **k: "最终报告")
    assert lead_aggregate("team-lead", "结果1\n结果2") == "最终报告"


def test_lead_aggregate_budget_forwarded(monkeypatch):
    captured = {}

    def fake(profile, msg, *, max_turns, run_budget, toolsets, timeout=None):
        captured.update(profile=profile, mt=max_turns, rb=run_budget, ts=toolsets)
        return "报告"

    monkeypatch.setattr("scheduler.leader.chat_budgeted", fake)
    lead_aggregate("team-lead", "结果")
    assert captured["profile"] == "team-lead"
    assert captured["mt"] == 8
    assert captured["rb"] == 120
    assert captured["ts"] == ["file", "skills"]