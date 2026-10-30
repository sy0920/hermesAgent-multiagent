"""Tests for scheduler.executor — budgeted expert execution."""

import pytest

from scheduler.executor import (
    EXECUTOR_MAX_TURNS,
    EXECUTOR_RUN_SECONDS,
    TOOLSET_WHITELIST,
    ExpertExecutionError,
    run_expert,
)


def test_run_expert_forwards_budget(monkeypatch):
    captured = {}

    def fake(profile, msg, *, max_turns, run_budget, toolsets, timeout=None):
        captured.update(profile=profile, msg=msg, mt=max_turns, rb=run_budget, ts=toolsets)
        return "输出"

    monkeypatch.setattr("scheduler.executor.chat_budgeted", fake)
    out = run_expert("researcher-a", "调研X", "上下文")
    assert out == "输出"
    assert captured["profile"] == "researcher-a"
    assert captured["mt"] == EXECUTOR_MAX_TURNS
    assert captured["rb"] == EXECUTOR_RUN_SECONDS
    assert captured["ts"] == TOOLSET_WHITELIST
    assert "调研X" in captured["msg"]
    assert "上下文" in captured["msg"]


def test_run_expert_failure_raises(monkeypatch):
    def fake(*a, **k):
        raise Exception("boom")

    monkeypatch.setattr("scheduler.executor.chat_budgeted", fake)
    with pytest.raises(ExpertExecutionError):
        run_expert("a", "i", "c")


def test_run_expert_constants():
    assert EXECUTOR_MAX_TURNS == 10
    assert EXECUTOR_RUN_SECONDS == 180
    assert "web" in TOOLSET_WHITELIST, "experts need web tools to research"
    for banned in ("delegate", "kanban", "send_message"):
        assert banned not in TOOLSET_WHITELIST, f"{banned} must never be whitelisted"


def test_run_expert_only_via_chat_budgeted(monkeypatch):
    """Review guard: executor must not import hermes subprocess runner."""
    import importlib
    import inspect

    import scheduler.executor as m
    importlib.reload(m)
    src = inspect.getsource(m)
    assert "import subprocess" not in src
    assert "run_hermes" not in src  # no unbudgeted Hermes path
    assert "execute_kanban_task" not in src