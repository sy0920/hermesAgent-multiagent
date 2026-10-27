"""Expert-team orchestration (Planner/Executor split).

An expert team is a named group of expert profiles driven by an
orchestrator ("team lead"). The team lead is the *Planner*: it reads the
user request and returns a structured JSON plan describing which tasks
each member should do and how they depend on each other. The backend is
the *Executor*: it turns that plan into kanban tasks and creates them.

If the planner's output is unparsable, references an unknown member, or
the orchestrator call fails, the executor falls back to a default tree so
the demo always produces a working board.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import uuid

from fastapi import APIRouter, HTTPException

from app.hermes_client import (
    HermesError,
    execute_kanban_task,
    kanban_create,
    kanban_list,
    kanban_show,
    run_hermes,
)
from app.schemas import (
    KanbanTask,
    TeamFinal,
    TeamInvokeRequest,
    TeamOut,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

# The team lead is the orchestrator profile; members are derived from the
# expert registry at request time (excludes the orchestrator itself).
_TEAM_DEFS = [
    {
        "id": "research",
        "display_name": "全栈研究团",
        "orchestrator": "team-lead",
    }
]

DEFAULT_WORKSPACE = os.environ.get(
    "HERMES_TEAM_WORKSPACE",
    os.path.expanduser("~/workspace/lab-share"),
)

# Runtime bookkeeping for the advance loop (single-process, non-persistent).
_recent_dispatch: dict[str, float] = {}

ADVANCE_INTERVAL_SECONDS = 5.0
RECENT_DISPATCH_WINDOW_SECONDS = 120.0

_PLAN_PROMPT = (
    "你是全栈研究团的团长。用户需求：{request}\n\n"
    "可以选择的成员：{members}\n\n"
    "请**只输出一个 JSON 计划**（不要解释、不要调用任何工具），用于把需求拆成任务。"
    "格式：\n"
    "{{\"tasks\": [{{\"title\": \"任务标题\", \"assignee\": \"成员名\", "
    "\"parents\": [任务序号], \"body\": \"输出要求\", \"final\": true}}]}}\n"
    "规则：\n"
    "- assignee 必须是上面给出的成员之一\n"
    "- parents 是**之前任务在数组中的序号**（0 起），表示依赖\n"
    "- 恰好一个任务带 \"final\": true 作为最终交付\n"
    "- 根据需求性质合理拆分（调研/开发/审核/汇总均可）\n"
)


def _registered_expert_ids() -> list[str]:
    """All expert profile ids from the registry (used for team membership)."""
    from app.experts import list_experts

    results = list_experts()
    return [e.id for e in results]


def _get_team(team_id: str) -> dict:
    for team in _TEAM_DEFS:
        if team["id"] == team_id:
            members = [
                m for m in _registered_expert_ids() if m != team["orchestrator"]
            ]
            if not members:
                members = ["researcher-a", "researcher-b", "reviewer", "writer"]
            team["members"] = members
            return team
    raise HTTPException(status_code=404, detail=f"专家团 {team_id} 不存在")


def list_teams() -> list[TeamOut]:
    return [
        TeamOut(
            id=t["id"],
            display_name=t["display_name"],
            members=_get_team(t["id"])["members"],
        )
        for t in _TEAM_DEFS
    ]


def _extract_plan(text: str) -> dict | None:
    """Pull a JSON plan out of the LLM reply.

    Tolerates prose around the JSON and a ```json fence. Returns None when
    the reply contains no usable JSON object.
    """
    if not text:
        return None
    # Prefer content inside a json fence if present.
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate = fence.group(1) if fence else text
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        data = json.loads(candidate[start : end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("tasks"), list):
        return None
    return data


def _validate_plan(data: dict, members: list[str]) -> bool:
    """A plan is usable when every assignee is a member and parents refer
    to earlier tasks (no forward/self references)."""
    tasks = data["tasks"]
    if not tasks:
        return False
    finals = 0
    for i, t in enumerate(tasks):
        if not isinstance(t, dict):
            return False
        if not isinstance(t.get("title"), str) or not t["title"].strip():
            return False
        assignee = t.get("assignee")
        if assignee not in members:
            return False
        for p in t.get("parents") or []:
            if not isinstance(p, int) or p < 0 or p >= i:
                return False
        if t.get("final"):
            finals += 1
    return finals == 1


def _team_workspace() -> str:
    """A persistent per-call workspace dir so outputs survive task completion."""
    run_dir = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    return f"dir:{DEFAULT_WORKSPACE}/{run_dir}"


def _build_from_plan(data: dict, fallback_request: str) -> str | None:
    """Create kanban tasks per the plan; return the final task id, or None
    on creation failure."""
    ws = _team_workspace()
    try:
        ids: list[str] = []
        final_id: str | None = None
        for t in data["tasks"]:
            parents = [ids[p] for p in (t.get("parents") or [])]
            task_id = kanban_create(
                t["title"],
                assignee=t["assignee"],
                parent_ids=parents,
                body=t.get("body") or f"需求: {fallback_request[:120]}",
                priority=1 if t.get("final") else 2,
                workspace=ws,
            )
            ids.append(task_id)
            if t.get("final"):
                final_id = task_id
        return final_id
    except HermesError:
        return None


def _build_default_tree(request: str) -> str:
    """Deterministic fallback tree: tech + case -> review -> final report."""
    ws = _team_workspace()
    tech_id = kanban_create(
        f"调研: {request[:50]} (技术架构)",
        assignee="researcher-a",
        body=f"输出到 {DEFAULT_WORKSPACE}/tech-research.md\n\n{request}",
        priority=2,
        workspace=ws,
    )
    case_id = kanban_create(
        f"调研: {request[:50]} (商业案例)",
        assignee="researcher-b",
        body=f"输出到 {DEFAULT_WORKSPACE}/case-research.md\n\n{request}",
        priority=2,
        workspace=ws,
    )
    review_id = kanban_create(
        f"审核: {request[:50]} (质量把关)",
        assignee="reviewer",
        parent_ids=[tech_id, case_id],
        body=f"输出到 {DEFAULT_WORKSPACE}/review-report.md",
        priority=2,
        workspace=ws,
    )
    final_id = kanban_create(
        f"综合报告: {request[:50]}",
        assignee="writer",
        parent_ids=[review_id],
        body=f"输出最终报告到 {DEFAULT_WORKSPACE}/final-report.md",
        priority=1,
        workspace=ws,
    )
    return final_id


def invoke_team(team_id: str, request: str) -> dict:
    """Ask the planner (team lead) for a task plan, then execute it.

    Planner errors degrade to the default tree instead of failing loudly.
    """
    team = _get_team(team_id)
    orchestrator = team["orchestrator"]

    final_id: str | None = None
    try:
        members = team["members"]
        reply = run_hermes(
            [
                "-p",
                orchestrator,
                "chat",
                "-q",
                _PLAN_PROMPT.format(request=request, members=", ".join(members)),
            ],
            timeout=60,
        )
        plan = _extract_plan(reply)
        if plan is not None and _validate_plan(plan, members):
            final_id = _build_from_plan(plan, request)
    except (HermesError, Exception):
        final_id = None

    if final_id is None:
        final_id = _build_default_tree(request)

    # Auto-dispatch ready tasks in parallel (roots will run immediately).
    advance_once()

    return {"orchestrator_task_id": final_id}


def advance_once() -> int:
    """Dispatch newly-ready tasks; return the number dispatched.

    A task is dispatchable when its status is 'ready' and it has not been
    dispatched within RECENT_DISPATCH_WINDOW_SECONDS. Dependencies are
    handled by Hermes: a task stays blocked until its parents are done,
    at which point it transitions to ready and this loop picks it up.
    """
    try:
        rows = kanban_list()
    except HermesError:
        return 0
    dispatched = 0
    now = time.time()
    for row in rows:
        if row.get("status") != "ready":
            continue
        task_id = row.get("id")
        assignee = row.get("assignee")
        if not task_id or not assignee:
            continue
        last = _recent_dispatch.get(task_id, 0.0)
        if now - last < RECENT_DISPATCH_WINDOW_SECONDS:
            continue
        _recent_dispatch[task_id] = now
        threading.Thread(
            target=_dispatch_worker_safe,
            args=(assignee, task_id),
            daemon=True,
        ).start()
        dispatched += 1
    return dispatched


def _dispatch_worker_safe(assignee: str, task_id: str) -> None:
    """Run a worker in a background thread; failures are logged, not raised."""
    try:
        execute_kanban_task(assignee, task_id, timeout=300)
    except HermesError as exc:
        logger.warning("auto-dispatch worker failed for %s: %s", task_id, exc)


def _advance_loop() -> None:
    """Background loop that keeps the board moving while the gateway is off."""
    while True:
        try:
            advance_once()
        except Exception as exc:  # noqa: BLE001 - loop must survive errors
            logger.warning("advance loop error: %s", exc)
        time.sleep(ADVANCE_INTERVAL_SECONDS)


_advance_thread: threading.Thread | None = None


def ensure_advance_loop() -> None:
    """Start the background advance loop exactly once per process."""
    global _advance_thread
    if _advance_thread is not None and _advance_thread.is_alive():
        return
    _advance_thread = threading.Thread(target=_advance_loop, daemon=True)
    _advance_thread.start()
    logger.info("kanban advance loop started (interval=%ss)", ADVANCE_INTERVAL_SECONDS)


def team_tasks(team_id: str) -> list[KanbanTask]:
    """All tasks currently visible on the board (the whole board is shared)."""
    _get_team(team_id)
    from app.kanban import list_tasks

    return list_tasks()


def team_final(team_id: str) -> TeamFinal:
    """Find the consolidated report: a done task whose metadata has 'final'."""
    _get_team(team_id)
    try:
        rows = kanban_list()
    except HermesError:
        return TeamFinal(report=None)
    for row in rows:
        if row.get("status") != "done":
            continue
        try:
            detail = kanban_show(row["id"])
        except HermesError:
            continue
        meta = detail.get("metadata") or {}
        if meta.get("final"):
            return TeamFinal(report=meta["final"])
    return TeamFinal(report=None)


@router.get("/teams", response_model=list[TeamOut])
def api_list_teams():
    return list_teams()


@router.post("/teams/{team_id}/invoke", response_model=dict)
def api_invoke_team(team_id: str, payload: TeamInvokeRequest):
    return invoke_team(team_id, payload.request)


@router.get("/teams/{team_id}/tasks", response_model=list[KanbanTask])
def api_team_tasks(team_id: str):
    return team_tasks(team_id)


@router.get("/teams/{team_id}/final", response_model=TeamFinal)
def api_team_final(team_id: str):
    return team_final(team_id)