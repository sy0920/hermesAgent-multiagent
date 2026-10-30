"""Scheduler HTTP API: sessions, plan confirm, resume.

These are thin wrappers over the engine — the state machine and task
ledger live in scheduler.engine/db.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException

from app.team_store import TeamStore
from scheduler import db
from scheduler import engine

router = APIRouter(prefix="/api")


def _group_config_hook(group_id: str) -> dict:
    """Resolve group config from the teams registry for the engine."""
    team = TeamStore().get(group_id)
    if team is None:
        return {"enable_plan_confirm": False, "members": [], "leader": ""}
    return {
        "enable_plan_confirm": False,
        "members": list(team.members),
        "leader": team.leader,
    }


def ensure_group_config_hook() -> None:
    engine._set_group_config_hook(_group_config_hook)


def create_session(team_id: str, user_query: str) -> str:
    """Create a new orchestrator session for a team."""
    team = TeamStore().get(team_id)
    if team is None:
        raise HTTPException(status_code=404, detail=f"专家团 {team_id} 不存在")
    ensure_group_config_hook()
    session_id = f"s_{uuid.uuid4().hex[:8]}"
    db.create_session(session_id, team_id, user_query)
    # Kick off planning on the next loop tick.
    engine.advance_sessions()
    return session_id


def get_session(session_id: str) -> dict:
    session = db.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session 不存在")
    session["subtasks"] = db.list_subtasks(session_id, session["round_no"])
    return session


def confirm_plan(session_id: str, decision: str, feedback: str = "") -> dict:
    engine.handle_plan_confirm(session_id, decision, feedback)
    return get_session(session_id)


def resume_session(session_id: str, feedback: str) -> dict:
    engine.request_resume(session_id, feedback)
    engine.advance_sessions()
    return get_session(session_id)


@router.post("/teams/{team_id}/sessions")
def api_create_session(team_id: str, payload: dict):
    return {"session_id": create_session(team_id, payload.get("user_query", ""))}


@router.get("/sessions/{session_id}")
def api_get_session(session_id: str):
    return get_session(session_id)


@router.post("/sessions/{session_id}/confirm")
def api_confirm_plan(session_id: str, payload: dict):
    return confirm_plan(
        session_id,
        payload.get("decision", "confirm"),
        payload.get("feedback", ""),
    )


@router.post("/sessions/{session_id}/resume")
def api_resume_session(session_id: str, payload: dict):
    return resume_session(session_id, payload.get("feedback", ""))