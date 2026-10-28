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
        return ("回复文本", "local-new-1")

    monkeypatch.setattr("app.experts.expert_chat", fake_chat)
    monkeypatch.setattr("app.experts.profile_list", lambda: ["sql", "researcher-a"])
    r = experts.expert_chat_route("sql", ChatRequest(message="你好"))
    assert r.reply == "回复文本"
    assert r.session_id == "local-new-1"
    assert captured["sid"] is None


def test_expert_chat_resume_session(monkeypatch):
    captured = {}

    def fake_chat(p, m, session_id=None):
        captured["p"] = p
        captured["m"] = m
        captured["sid"] = session_id
        return ("继续回复", "s_1")

    monkeypatch.setattr("app.experts.expert_chat", fake_chat)
    monkeypatch.setattr("app.experts.profile_list", lambda: ["sql"])
    r = experts.expert_chat_route("sql", ChatRequest(message="继续", session_id="s_1"))
    assert captured["sid"] == "s_1"
    assert r.session_id == "s_1"


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


def test_expert_chat_extracts_session_from_stdout(monkeypatch):
    """The CLI session line is parsed into the returned session_id."""

    class FakeProc:
        returncode = 0
        stdout = "Query: 你好\n\n☤ Hermes\n回复文本\n\nSession: local-abc123\n"
        stderr = ""

    monkeypatch.setattr(
        "app.hermes_client.subprocess.run",
        lambda a, **k: FakeProc(),
    )
    from app.hermes_client import expert_chat

    reply, sid = expert_chat("sql", "你好", session_id=None)
    assert reply == "回复文本"
    assert "abc123" in (sid or "")


def test_expert_chat_strips_thought_and_trailer(monkeypatch):
    """Chain-of-thought lines and Hermes' stats trailer are cleaned out."""

    class FakeProc:
        returncode = 0
        stdout = (
            "Query: hi\n\n"
            "The user asks in Chinese meanwhile the system wants tools...\n"
            "∴ Thought for 1s · the user greets\n"
            "☤ Hermes\n"
            "你好！我是研究员。\n\n\n\n"
            "我可以帮你做事：\n"
            "hermes --resume local-x -p researcher-a\n"
            "Title: hi\nDuration: 5s\nMessages: 2 (1 user, 0 tool calls)\n"
            "Session: local-x\n"
        )
        stderr = ""

    monkeypatch.setattr(
        "app.hermes_client.subprocess.run",
        lambda a, **k: FakeProc(),
    )
    from app.hermes_client import expert_chat

    reply, sid = expert_chat("researcher-a", "hi", session_id=None)
    # Chain-of-thought (any prefix) must be gone — only reply after marker.
    assert "The user asks" not in reply
    assert "Thought" not in reply
    # Fresh reply body intact.
    assert "你好！我是研究员。" in reply
    assert "我可以帮你做事：" in reply
    # Trailer + stats gone.
    assert "Title:" not in reply
    assert "Duration" not in reply
    assert "Messages" not in reply
    assert "hermes --resume" not in reply
    # Blank runs collapsed (no triple newlines).
    assert "\n\n\n" not in reply
    assert sid == "local-x"


def test_extract_reply_fallback_without_marker():
    """No ☤ marker → still returns content, dropping Query/chatter lines."""
    from app.hermes_client import _extract_reply

    out = "Query: hi\n⚠ some warning\n你好！\n\nTitle: hi\nDuration: 1s\n"
    reply = _extract_reply(out)
    assert "你好！" in reply
    assert "Query:" not in reply
    assert "Title:" not in reply


def test_expert_chat_new_session_route_returns_nonnull_session(monkeypatch):
    """New conversations must produce a usable session_id (spec contract)."""
    monkeypatch.setattr(
        "app.experts.expert_chat",
        lambda p, m, session_id=None: ("回复", "local-new-xyz"),
    )
    monkeypatch.setattr("app.experts.profile_list", lambda: ["sql"])
    r = experts.expert_chat_route("sql", ChatRequest(message="你好"))
    assert r.session_id == "local-new-xyz"