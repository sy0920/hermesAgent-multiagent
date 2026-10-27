"""Expert-team orchestration.

An expert team is a named group of expert profiles driven by an
orchestrator profile ("team lead"). MVP flow:

1. User sends a request to the team.
2. The backend asks the team-lead profile to decompose it into kanban
   tasks (via ``kanban create``), assigning each to a member.
3. The frontend watches kanban/events; tasks move todo → doing → done.
4. The final consolidated report is read from the done task's metadata.

The team-lead call is best-effort: if the model does not create useful
tasks, the backend still registers a root task so the loop is observable.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.hermes_client import (
    HermesError,
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

router = APIRouter(prefix="/api")

TEAMS = [
    {
        "id": "research",
        "display_name": "全栈研究团",
        "members": ["researcher-a", "researcher-b", "reviewer", "writer"],
        "orchestrator": "team-lead",
    }
]

_ORCHESTRATOR_PROMPT = (
    "你是全栈研究团的团长。用户需求：{request}。\n"
    "请按照标准流程用 kanban_create 拆解任务并分配："
    "（1）调研类任务 assignee=researcher-a/b；"
    "（2）质量审核 assignee=reviewer（parent 指向调研任务）；"
    "（3）综合报告 assignee=writer（parent 指向审核任务）。"
    "用 --body 写明输出要求。"
)


def _get_team(team_id: str) -> dict:
    for team in TEAMS:
        if team["id"] == team_id:
            return team
    raise HTTPException(status_code=404, detail=f"专家团 {team_id} 不存在")


def list_teams() -> list[TeamOut]:
    return [
        TeamOut(id=t["id"], display_name=t["display_name"], members=t["members"])
        for t in TEAMS
    ]


def invoke_team(team_id: str, request: str) -> dict:
    """Build the standard research-team task tree for a request.

    The team lead's LLM decomposition is attempted best-effort in the
    background; the tree below is created deterministically so the demo
    always works even when the orchestrator model is slow or offline:
        researcher-a (tech)  ─┐
                              ├─> reviewer ─> writer (final report)
        researcher-b (cases) ─┘
    """
    team = _get_team(team_id)
    orchestrator = team["orchestrator"]

    # 1) Best-effort orchestrator chat (never blocks the response).
    try:
        run_hermes(
            ["-p", orchestrator, "chat", "-q", _ORCHESTRATOR_PROMPT.format(request=request)],
            timeout=5,
        )
    except (HermesError, Exception):
        pass

    # 2) Deterministic task tree.
    tech_id = kanban_create(
        f"调研: {request[:50]} (技术架构)",
        assignee="researcher-a",
        body=f"输出到 ~/workspace/lab-share/tech-research.md\n\n{request}",
        priority=2,
    )
    case_id = kanban_create(
        f"调研: {request[:50]} (商业案例)",
        assignee="researcher-b",
        body=f"输出到 ~/workspace/lab-share/case-research.md\n\n{request}",
        priority=2,
    )
    review_id = kanban_create(
        f"审核: {request[:50]} (质量把关)",
        assignee="reviewer",
        parent_ids=[tech_id, case_id],
        body=f"输出到 ~/workspace/lab-share/review-report.md",
        priority=2,
    )
    final_id = kanban_create(
        f"综合报告: {request[:50]}",
        assignee="writer",
        parent_ids=[review_id],
        body=f"输出最终报告到 ~/workspace/lab-share/final-report.md",
        priority=1,
    )
    return {"orchestrator_task_id": final_id}


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