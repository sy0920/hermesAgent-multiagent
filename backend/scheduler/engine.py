"""Central orchestrator engine — the pure-code dispatcher.

LOOP (advance_sessions) drives group_session through its state machine on
every poll:

    submitting → planning → waiting_confirm ⇄ running → aggregating
               → finished → resuming → running (next round)

Key facts:
- Only this module writes kanban (``_sync_kanban``); experts never touch it.
- Failed subtasks are marked, never auto-redispatched.
- Leader calls go through scheduler.leader; expert calls through
  scheduler.executor — both budgeted Hermes agents.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any, Callable

from app.hermes_client import kanban_create
from scheduler import db
from scheduler.leader import lead_aggregate, lead_plan
from scheduler.executor import run_expert

logger = logging.getLogger(__name__)

ENGINE_POLL_SECONDS = 3.0
TERMINAL = {"success", "failed"}


# Injected group config resolver — the engine does not import teams.py to
# keep itself independent and testable. Production wires this in via
# engines hookup in the API layer.
def _group_config(group_id: str) -> dict[str, Any]:
    return {"enable_plan_confirm": False, "members": [], "leader": ""}


def _set_group_config_hook(fn: Callable[[str], dict[str, Any]]) -> None:
    global _group_config
    _group_config = fn


def ensure_engine_loop() -> None:
    thread = threading.Thread(target=_loop, daemon=True)
    thread.start()


def _loop() -> None:
    while True:
        try:
            advance_sessions()
        except Exception as exc:  # noqa: BLE001 - loop survives
            logger.warning("engine loop error: %s", exc)
        time.sleep(ENGINE_POLL_SECONDS)


# ---------------------------------------------------------------------------
# Planning: submitting → planning → (waiting_confirm | running)
# ---------------------------------------------------------------------------


def _start_planning(session: dict[str, Any]) -> None:
    group = _group_config(session["group_id"])
    roster = ", ".join(group.get("members") or [])
    history = ""
    if session.get("final_report"):
        history = session["final_report"]
    db.update_session(session["session_id"], status="planning")
    plan = lead_plan(
        group.get("leader", ""),
        session.get("user_query", ""),
        roster,
        history=history,
        round_no=session.get("round_no", 1),
    )
    if plan is None:
        # Leader produced nothing usable — surface as error, user can edit.
        db.update_session(session["session_id"], status="error")
        return
    db.update_session(
        session["session_id"],
        status="planning",
        plan_json=json.dumps(plan, ensure_ascii=False),
    )
    subtasks = plan.get("subtasks") or []
    if not subtasks:
        # Empty plan: nothing to do → finished (else session hangs in running).
        db.update_session(session["session_id"], status="finished")
        return
    _materialize_subtasks(session["session_id"], session["round_no"], subtasks)
    if group.get("enable_plan_confirm"):
        db.update_session(session["session_id"], status="waiting_confirm")
    else:
        db.update_session(session["session_id"], status="running")


def _materialize_subtasks(session_id: str, round_no: int, subtasks: list[dict]) -> None:
    for i, t in enumerate(subtasks):
        subtask_id = f"{session_id}-{round_no}-{i}"
        # Validate deps: only reference existing earlier task ids in THIS
        # round; anything else (missing index / self / future) is dropped
        # so the session can never dead-lock on an unresolvable dep.
        valid_deps = [
            f"{session_id}-{round_no}-{d}"
            for d in (t.get("deps") or [])
            if isinstance(d, int) and 0 <= d < i
        ]
        db.create_subtask(
            db.SubtaskRow(
                subtask_id=subtask_id,
                session_id=session_id,
                round_no=round_no,
                expert_id=t.get("expert_id", ""),
                title=t.get("title") or (t.get("instruction") or "")[:80] or "任务",
                instruction=t.get("instruction", ""),
                input_context=t.get("input_context", ""),
                deps=valid_deps,
                status="pending",
            )
        )


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


def _subtask_ready(sub: dict[str, Any]) -> bool:
    if sub["status"] != "pending":
        return False
    for dep in sub["deps"]:
        dep_sub = db.get_subtask(dep)
        if dep_sub is None or dep_sub["status"] not in TERMINAL:
            return False
    return True


def _mark_dep_failed(sub: dict[str, Any]) -> bool:
    """If any dep is failed OR unresolvable, this subtask is blocked
    forever → mark it failed so the session cannot hang."""
    for dep in sub["deps"]:
        dep_sub = db.get_subtask(dep)
        if dep_sub is None:
            return True  # unresolvable dep → fail
        if dep_sub["status"] == "failed":
            return True
    return False


def _dispatch_ready(session_id: str, round_no: int, max_parallel: int) -> int:
    subtasks = db.list_subtasks(session_id, round_no)
    running_by_expert: dict[str, int] = {}
    running_count = 0
    for s in subtasks:
        if s["status"] == "running":
            running_count += 1
            running_by_expert[s["expert_id"]] = running_by_expert.get(s["expert_id"], 0) + 1
    budget = max_parallel - running_count
    if budget <= 0:
        return 0
    # Per-expert concurrency cap (default 1 → one instance per expert).
    expert_cap = 1
    dispatched = 0
    for sub in subtasks:
        if dispatched >= budget:
            break
        if _mark_dep_failed(sub):
            db.update_subtask(sub["subtask_id"], status="failed")
            continue
        if not _subtask_ready(sub):
            continue
        if running_by_expert.get(sub["expert_id"], 0) >= expert_cap:
            continue  # this expert is busy
        db.update_subtask(sub["subtask_id"], status="running")
        running_by_expert[sub["expert_id"]] = running_by_expert.get(sub["expert_id"], 0) + 1
        running_count += 1
        threading.Thread(
            target=_run_worker,
            args=(sub["subtask_id"], sub["expert_id"], sub["instruction"], sub["input_context"]),
            daemon=True,
        ).start()
        dispatched += 1
    return dispatched


def _run_worker(subtask_id: str, expert_id: str, instruction: str, context: str) -> None:
    try:
        output = run_expert(expert_id, instruction, context)
        db.update_subtask(subtask_id, status="success", output=output)
    except Exception as exc:  # noqa: BLE001 - mark failed, never retry
        logger.warning("expert %s failed on %s: %s", expert_id, subtask_id, exc)
        db.update_subtask(subtask_id, status="failed")


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def _aggregate(session: dict[str, Any]) -> None:
    subtasks = db.list_subtasks(session["session_id"], session["round_no"])
    results = "\n\n".join(
        f"## {s['title']}（{s['status']}）\n{s['output']}" for s in subtasks
    )
    group = _group_config(session["group_id"])
    report = lead_aggregate(group.get("leader", ""), results)
    db.update_session(
        session["session_id"],
        status="finished",
        final_report=report or results,  # degraded to collected results
    )


# ---------------------------------------------------------------------------
# Main loop entry
# ---------------------------------------------------------------------------


def advance_sessions() -> int:
    """One pass over all sessions; returns number of sessions touched."""
    touched = 0
    for session in db.list_sessions():
        status = session["status"]
        if status == "submitting":
            _start_planning(session)
            touched += 1
        elif status == "planning":
            pass  # leader call is synchronous inside _start_planning
        elif status == "waiting_confirm":
            continue  # wait for user decision
        elif status == "running":
            _sync_kanban(session["session_id"], session["round_no"])
            _dispatch_ready(session["session_id"], session["round_no"], max_parallel=4)
            subs = db.list_subtasks(session["session_id"], session["round_no"])
            if subs and all(s["status"] in TERMINAL for s in subs):
                db.update_session(session["session_id"], status="aggregating")
            touched += 1
        elif status == "aggregating":
            _aggregate(session)
            touched += 1
        elif status == "resuming":
            _start_planning(session)
            touched += 1
        elif status in ("finished", "error"):
            pass
    return touched


def handle_plan_confirm(session_id: str, decision: str, feedback: str = "") -> None:
    """User response to a waiting_confirm plan. decision: confirm|regenerate|edit."""
    session = db.get_session(session_id)
    if not session or session["status"] != "waiting_confirm":
        return
    if decision in ("regenerate", "edit"):
        # Replace the current round's subtasks entirely (avoid id collisions
        # with the old rows) and re-plan.
        db.delete_subtasks(session_id, session["round_no"])
        db.update_session(session_id, status="planning")
        if feedback:
            db.update_session(session_id, user_query=session["user_query"] + "\n[反馈]" + feedback)
        _start_planning(db.get_session(session_id))
    elif decision == "confirm":
        db.update_session(session_id, status="running")


def request_resume(session_id: str, feedback: str) -> None:
    """User is unsatisfied: start a new round on top of the last report."""
    session = db.get_session(session_id)
    if not session or session["status"] != "finished":
        return
    db.update_session(
        session_id,
        status="resuming",
        round_no=session["round_no"] + 1,
        user_query=session["user_query"] + "\n[反馈]" + feedback,
    )


# ---------------------------------------------------------------------------
# Kanban mirroring (single writer)
# ---------------------------------------------------------------------------


def _sync_kanban(session_id: str, round_no: int) -> None:
    """One-way mirror: subtask state → kanban task (display only).

    Each subtask creates its kanban row exactly once per process (tracked
    in ``_kanban_mirrored``); repeated polls never duplicate.
    """
    for sub in db.list_subtasks(session_id, round_no):
        if sub["subtask_id"] in _kanban_mirrored:
            continue
        _kanban_mirrored.add(sub["subtask_id"])
        try:
            kanban_create(
                f"[{session_id}] {sub['title']}",
                assignee=sub["expert_id"] or "unassigned",
                body=sub["instruction"][:200],
                priority=2,
            )
        except Exception as exc:  # noqa: BLE001 - mirror must not break loop
            logger.warning("kanban mirror failed for %s: %s", sub["subtask_id"], exc)


# Subtasks already mirrored to kanban this process (dedup guard for C2).
_kanban_mirrored: set[str] = set()