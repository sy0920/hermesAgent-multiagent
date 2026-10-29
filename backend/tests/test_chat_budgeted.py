"""Tests for chat_budgeted — the token-safe Hermes call wrapper."""

import pytest

from app.hermes_client import chat_budgeted


class FakeProc:
    returncode = 0
    stdout = "回复\n"
    stderr = ""


class FakeGateway:
    def poll(self):
        return None  # gateway "running"

    def __init__(self, *a, **k):
        pass


def test_chat_budgeted_builds_budget_args(monkeypatch):
    captured = []

    def fake_run(args, **kw):
        captured.append(args)
        return FakeProc()

    monkeypatch.setattr("app.hermes_client.subprocess.run", fake_run)
    monkeypatch.setattr("app.hermes_client.subprocess.Popen", FakeGateway)
    monkeypatch.setattr("app.hermes_client.time.sleep", lambda s: None)
    chat_budgeted(
        "researcher-a",
        "调研X",
        max_turns=10,
        run_budget=180,
        toolsets=["file", "skills", "terminal"],
    )
    joined = " ".join(captured[0])
    assert "--max-turns" in joined and "10" in joined
    assert "--run-budget" in joined and "180" in joined
    assert "-t" in joined and "file,skills,terminal" in joined
    assert "-Q" in joined
    assert "-p" in joined and "researcher-a" in joined
    assert "调研X" in joined


def test_chat_budgeted_no_toolsets_omits_t(monkeypatch):
    captured = []

    def fake_run(args, **kw):
        captured.append(args)
        return FakeProc()

    monkeypatch.setattr("app.hermes_client.subprocess.run", fake_run)
    monkeypatch.setattr("app.hermes_client.subprocess.Popen", FakeGateway)
    monkeypatch.setattr("app.hermes_client.time.sleep", lambda s: None)
    chat_budgeted("a", "m", max_turns=5, run_budget=60, toolsets=None)
    joined = " ".join(captured[0])
    assert "-t file" not in joined  # no toolset arg when none given
    assert " --max-turns " in joined and "5" in joined
    assert " --run-budget " in joined and "60" in joined


def test_chat_budgeted_timeout_defaults_to_run_budget_plus_30(monkeypatch):
    captured = {}

    def fake_run(args, timeout=None, **kw):
        captured["timeout"] = timeout
        return FakeProc()

    monkeypatch.setattr("app.hermes_client.subprocess.run", fake_run)
    monkeypatch.setattr("app.hermes_client.subprocess.Popen", FakeGateway)
    monkeypatch.setattr("app.hermes_client.time.sleep", lambda s: None)
    chat_budgeted("a", "m", max_turns=5, run_budget=60)
    assert captured["timeout"] == 90


def test_chat_budgeted_explicit_timeout_wins(monkeypatch):
    captured = {}

    def fake_run(args, timeout=None, **kw):
        captured["timeout"] = timeout
        return FakeProc()

    monkeypatch.setattr("app.hermes_client.subprocess.run", fake_run)
    monkeypatch.setattr("app.hermes_client.subprocess.Popen", FakeGateway)
    monkeypatch.setattr("app.hermes_client.time.sleep", lambda s: None)
    chat_budgeted("a", "m", max_turns=5, run_budget=60, timeout=200)
    assert captured["timeout"] == 200