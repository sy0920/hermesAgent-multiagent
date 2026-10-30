"""Team-lead orchestration: plan generation and aggregation.

The leader is a budgeted Hermes agent instance that only PRODUCES TEXT:
a structured task plan (JSON) in `lead_plan`, or a consolidated final
report in `lead_aggregate`. It never dispatches anything itself — the
scheduler's engine interprets the plan.
"""

from __future__ import annotations

import json
import re
from typing import Callable

from app.hermes_client import chat_budgeted

LEADER_PLAN_TURNS = 5
LEADER_PLAN_SECONDS = 60
LEADER_AGGREGATE_TURNS = 8
LEADER_AGGREGATE_SECONDS = 120
LEADER_TOOLSETS = ["file", "skills"]

PLAN_PROMPT_TEMPLATE = (
    "你是专家团团长。用户需求：{user_query}\n\n"
    "可选择的成员（只能从这些专家分配任务）：{roster}\n"
    "{history}\n"
    "现在是第 {round_no} 轮规划。\n\n"
    "请**只输出一个 JSON 方案**（不要解释、不要额外文字、不要调用工具）：\n"
    "{{\"summary\": \"整体方案简述\", \"subtasks\": ["
    "{{\"expert_id\": \"成员名\", \"instruction\": \"给专家的指令\", "
    "\"input_context\": \"给该专家的精简上下文（只含必要信息）\", "
    "\"deps\": [依赖的子任务序号，0起], \"parallel_group\": \"可并行分组\"}}]}}\n"
    "规则：\n"
    "- expert_id 必须是花名册中成员\n"
    "- 每个子任务给出精简 input_context（后台会按它裁剪，专家看不到完整对\n话）\n"
    "- 合理拆分任务并标记依赖（串行）与 parallel_group（并行）\n"
)

AGGREGATE_PROMPT_TEMPLATE = (
    "你是专家团团长。所有子任务已执行完成，以下是结果：\n\n{results}\n\n"
    "请综合复审：合并、校验、补全、交叉评审、统一文风，输出最终交付物"
    "（Markdown）。不要引入未在结果中出现的新事实。"
)


def _extract_plan_json(text: str) -> dict | None:
    """Pull a JSON object out of possibly-wrapped model output."""
    if not text:
        return None
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
    if not isinstance(data, dict):
        return None
    raw_tasks = data.get("subtasks")
    if raw_tasks is not None and not isinstance(raw_tasks, list):
        return None
    cleaned = []
    for t in raw_tasks or []:
        if not isinstance(t, dict):
            continue
        cleaned.append(
            {
                "expert_id": t.get("expert_id", ""),
                "instruction": t.get("instruction", ""),
                "input_context": t.get("input_context", ""),
                "deps": [d for d in (t.get("deps") or []) if isinstance(d, int)],
                "parallel_group": t.get("parallel_group"),
            }
        )
    return {"summary": data.get("summary", ""), "subtasks": cleaned}


def lead_plan(
    leader_expert_id: str,
    user_query: str,
    roster: str,
    history: str = "",
    round_no: int = 1,
    budget_fn: Callable | None = None,
) -> dict | None:
    """Ask the leader for a structured task plan (single budgeted call)."""
    history_block = f"上一轮已完成结果（供参考，规划新一轮增量修改）：\n{history}" if history else ""
    prompt = PLAN_PROMPT_TEMPLATE.format(
        user_query=user_query,
        roster=roster,
        history=history_block,
        round_no=round_no,
    )
    call = budget_fn or chat_budgeted
    try:
        text = call(
            leader_expert_id,
            prompt,
            max_turns=LEADER_PLAN_TURNS,
            run_budget=LEADER_PLAN_SECONDS,
            toolsets=LEADER_TOOLSETS,
        )
    except Exception:  # noqa: BLE001 — plan failure is recovered by caller
        return None
    return _extract_plan_json(text)


def lead_aggregate(
    leader_expert_id: str,
    results_text: str,
    budget_fn: Callable | None = None,
) -> str | None:
    """Ask the leader to review and consolidate all subtask results."""
    prompt = AGGREGATE_PROMPT_TEMPLATE.format(results=results_text)
    call = budget_fn or chat_budgeted
    try:
        return call(
            leader_expert_id,
            prompt,
            max_turns=LEADER_AGGREGATE_TURNS,
            run_budget=LEADER_AGGREGATE_SECONDS,
            toolsets=LEADER_TOOLSETS,
        )
    except Exception:  # noqa: BLE001
        return None