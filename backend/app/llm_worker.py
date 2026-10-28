"""Single-shot LLM worker — the token-safe executor.

Each task costs exactly ONE LLM completion:
    1. read the kanban task card (title/body/assignee/workspace)
    2. build a system prompt from the expert's SOUL.md + a short user prompt
       carrying the task body
    3. call the provider once
    4. write the reply to the task's workspace file

No Hermes agent is involved, so there is no tool loop that can run away.
Model params: an llm_client_factory is injected for testability; the
production factory is a thin OpenAI-compatible client.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable

DEFAULT_SYSTEM_TEMPLATE = (
    "你是专家 {expert_name}。\n"
    "按以下人设工作（如有 SOUL.md 内容则遵循之）：\n\n{soul}\n\n"
    "请完成被分配的任务，输出结构化的中文结果（Markdown）。"
)


class LlmClient:
    """OpenAI-compatible single-call client (zero retries, one request)."""

    def __init__(self, api_key: str, base_url: str, model: str):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model

    def chat_once(self, system_prompt: str, user_prompt: str) -> str:
        import urllib.request

        payload = json.dumps(
            {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.3,
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]


def _default_client_factory(api_key: str, base_url: str, model: str) -> LlmClient:
    return LlmClient(api_key, base_url, model)


def run_single_shot_worker(
    card: dict[str, Any],
    soul_text: str,
    model: str,
    api_key: str,
    base_url: str,
    llm_client_factory: Callable[..., Any] = _default_client_factory,
) -> str | None:
    """Execute one task via a single LLM call and persist the result.

    Returns the reply text (written to ``workspace/<task-id>.md``), or None
    if the fetch failed.
    """
    task_id = card.get("id", "task")
    title = card.get("title", "")
    body = card.get("body", "")
    assignee = card.get("assignee", "expert")
    workspace = card.get("workspace") or str(Path.home() / "hermes-workspace")

    system_prompt = DEFAULT_SYSTEM_TEMPLATE.format(expert_name=assignee, soul=soul_text)
    user_prompt = f"任务：{title}\n\n要求：{body}" if body else f"任务：{title}"

    client = llm_client_factory(api_key, base_url, model)
    try:
        reply = client.chat_once(system_prompt, user_prompt)
    except Exception:  # noqa: BLE001 — single-shot, fail without retry
        # One failed call is not worth retrying (token safety).
        return None

    # Persist the result next to the task workspace.
    ws = Path(workspace)
    ws.mkdir(parents=True, exist_ok=True)
    safe_id = task_id.replace("/", "_")
    out_file = ws / f"{safe_id}.md"
    out_file.write_text(reply, encoding="utf-8")

    # Mark the kanban task as done with a pointer to the result file.
    try:
        from app.task_result_store import mark_task_done

        mark_task_done(task_id, str(out_file), summary=reply[:200])
    except Exception:  # noqa: BLE001 — sidecar write must not fail the task
        pass
    return reply


def dispatch_single_shot(
    card: dict[str, Any],
    soul_text: str,
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
) -> str | None:
    """Convenience wrapper reading credentials from environment by default."""
    env = os.environ
    return run_single_shot_worker(
        card=card,
        soul_text=soul_text,
        model=model or env.get("MODEL", "deepseek-chat"),
        api_key=api_key or env.get("OPENAI_API_KEY", ""),
        base_url=base_url or env.get("OPENAI_BASE_URL", "https://api.deepseek.com/v1"),
    )