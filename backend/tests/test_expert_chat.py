"""Tests for the expert chat API (multi-turn session)."""

import pytest

from app import experts
from app.schemas import ChatRequest


def test_expert_chat_new_session(monkeypatch):
    captured = {}

    def fake_chat(p, m, session_id=None):
        captured["p"] = p
        captured["m"] = m
        captured["sid"] = session_id
        return "回复文本"

    monkeypatch.setattr("app.experts.expert_chat", fake_chat)
    monkeypatch.setattr("app.experts.profile_list", lambda: ["sql", "researcher-a"])
    r = experts.expert_chat_route("sql", ChatRequest(message="你好"))
    assert r.reply == "回复文本"
    assert captured["sid"] is None


def test_expert_chat_resume_session(monkeypatch):
    captured = {}

    def fake_chat(p, m, session_id=None):
        captured["p"] = p
        captured["m"] = m
        captured["sid"] = session_id
        return "继续回复"

    monkeypatch.setattr("app.experts.expert_chat", fake_chat)
    monkeypatch.setattr("app.experts.profile_list", lambda: ["sql"])
    r = experts.expert_chat_route("sql", ChatRequest(message="继续", session_id="s_1"))
    assert captured["sid"] == "s_1"


def test_expert_chat_unknown_profile_404(monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setattr("app.experts.profile_list", lambda: ["sql"])
    with pytest.raises(HTTPException) as exc_info:
        experts.expert_chat_route("ghost", ChatRequest(message="hi"))
    assert exc_info.value.status_code == 404


def test_expert_chat_builds_resume_args(monkeypatch):
    captured = []

    class FakeProc:
        returncode = 0
        stdout = "回复文本\n"
        stderr = ""

    monkeypatch.setattr(
        "app.hermes_client.subprocess.run",
        lambda a, **k: captured.append(a) or FakeProc(),
    )
    from app.hermes_client import expert_chat

    expert_chat("sql", "继续", session_id="s_1")
    joined = " ".join(captured[0])
    assert "--resume" in joined and "s_1" in joined
    assert "-p" in joined and "sql" in joined


def test_expert_chat_new_no_resume(monkeypatch):
    captured = []

    class FakeProc:
        returncode = 0
        stdout = "回复\n"
        stderr = ""

    monkeypatch.setattr(
        "app.hermes_client.subprocess.run",
        lambda a, **k: captured.append(a) or FakeProc(),
    )
    from app.hermes_client import expert_chat

    expert_chat("sql", "你好", session_id=None)
    joined = " ".join(captured[0])
    assert "--resume" not in joined
    assert "你好" in joined