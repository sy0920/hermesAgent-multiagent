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
    """Ask the team lead to decompose a request into kanban tasks."""
    team = _get_team(team_id)
    orchestrator = team["orchestrator"]

    create_err = None
    try:
        run_hermes(["-p", orchestrator, "chat", "-q", _ORCHESTRATOR_PROMPT.format(request=request)])
    except HermesError as exc:
        create_err = exc

    # Fallback root task so the loop is always observable, even if the
    # model produced nothing (or the call failed).
    try:
        root_id = kanban_create(
            f"专家团任务: {request[:60]}",
            assignee="writer",
            body=f"团队综合交付任务（团长拆解失败或未产出的兜底）\n\n{request}",
            priority=1,
        )
    except HermesError as exc:
        if create_err is not None:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        raise HTTPException(
            status_code=500,
            detail=f"团长调用与兜底建卡均失败: {exc}",
        ) from exc
    return {"orchestrator_task_id": root_id}


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