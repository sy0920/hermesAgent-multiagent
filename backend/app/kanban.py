"""Kanban bridge routes.

Reads the Hermes kanban task list and exposes it to the frontend with
children derivation (inverse of parents), a task detail endpoint, and a
manually-triggered worker runner.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncIterator

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse

from app.hermes_client import (
    HermesError,
    execute_kanban_task,
    kanban_list,
    kanban_show,
    kanban_unblock,
)
from app.schemas import KanbanRunResult, KanbanTask, KanbanTaskDetail

router = APIRouter(prefix="/api")

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 3.0


def list_tasks() -> list[KanbanTask]:
    """All tasks, with children derived from each task's parents."""
    rows = kanban_list()
    task_map: dict[str, KanbanTask] = {}
    for row in rows:
        task_map[row["id"]] = KanbanTask(
            id=row.get("id", ""),
            title=row.get("title", ""),
            status=row.get("status", "todo"),
            assignee=row.get("assignee"),
            parents=list(row.get("parents") or []),
        )
    for task in task_map.values():
        for parent in task.parents:
            if parent in task_map:
                task_map[parent].children.append(task.id)
    return list(task_map.values())


def task_detail(task_id: str) -> KanbanTaskDetail:
    """Full detail for one task (body / summary / metadata / runs)."""
    try:
        row = kanban_show(task_id)
    except HermesError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    parents = list(row.get("parents") or [])
    children = list(row.get("children") or [])
    return KanbanTaskDetail(
        id=row.get("id", task_id),
        title=row.get("title", ""),
        status=row.get("status", "todo"),
        assignee=row.get("assignee"),
        parents=parents,
        children=children,
        body=row.get("body", ""),
        summary=row.get("summary"),
        metadata=row.get("metadata") or {},
        runs=row.get("runs") or [],
    )


def run_task(task_id: str, background_tasks: BackgroundTasks | None = None) -> KanbanRunResult:
    """Arm a worker run for a task.

    The actual worker execution is scheduled onto ``background_tasks``
    (FastAPI's background mechanism) so the HTTP request returns
    immediately with status "started". When called without background
    tasks (tests, synchronous contexts) a no-op scheduler arms nothing;
    the routing layer always supplies one.
    """
    try:
        row = kanban_show(task_id)
    except HermesError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    assignee = row.get("assignee")
    if not assignee:
        raise HTTPException(status_code=400, detail="任务没有 assignee，无法执行")
    if background_tasks is not None:
        background_tasks.add_task(_run_worker, assignee, task_id)
    return KanbanRunResult(run_id=task_id)


def _run_worker(assignee: str, task_id: str) -> None:
    """Background entrypoint; errors are captured and logged, never raised."""
    try:
        execute_kanban_task(assignee, task_id)
    except HermesError as exc:
        # Surfacing to the user happens through the kanban status/SSE;
        # the worker failure is recorded on the task by Hermes itself.
        logger.warning("kanban worker failed for %s: %s", task_id, exc)


def unblock_task(task_id: str) -> dict:
    try:
        kanban_unblock(task_id)
    except HermesError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True}


async def _event_stream() -> AsyncIterator[str]:
    """Poll the kanban list (in a thread) and push diffs as SSE."""
    last = None
    while True:
        try:
            snapshot = [t.model_dump() for t in await asyncio.to_thread(list_tasks)]
        except HermesError:
            snapshot = last or []
        if snapshot != last:
            last = snapshot
            yield sse_frame(snapshot)
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


@router.get("/kanban/tasks", response_model=list[KanbanTask])
def api_list_tasks():
    return list_tasks()


@router.get("/kanban/tasks/{task_id}", response_model=KanbanTaskDetail)
def api_task_detail(task_id: str):
    return task_detail(task_id)


@router.post("/kanban/tasks/{task_id}/unblock", response_model=dict)
def api_unblock(task_id: str):
    return unblock_task(task_id)


@router.post("/tasks/{task_id}/run", response_model=KanbanRunResult)
def api_run_task(task_id: str, background_tasks: BackgroundTasks):
    return run_task(task_id, background_tasks=background_tasks)


@router.get("/kanban/events")
async def api_kanban_events():
    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def sse_frame(tasks: list[dict]) -> str:
    """Build a single SSE frame for a task snapshot (pure, testable)."""
    payload = {"type": "update", "tasks": tasks}
    return f"event: update\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"