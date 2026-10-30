"""Expert execution for the central orchestrator.

Each expert runs as a budgeted Hermes agent instance (single call, at most
``EXECUTOR_MAX_TURNS`` iterations, ``EXECUTOR_RUN_SECONDS`` wall-clock,
restricted to ``TOOLSET_WHITELIST``). This is a one-shot dispatch: failures
raise and are never retried by the caller's loop.
"""

from __future__ import annotations

from typing import Callable

from app.hermes_client import chat_budgeted

EXECUTOR_MAX_TURNS = 10
EXECUTOR_RUN_SECONDS = 180
TOOLSET_WHITELIST = ["file", "skills", "terminal"]


class ExpertExecutionError(RuntimeError):
    """Raised when an expert's single budgeted call fails."""


def run_expert(
    expert_id: str,
    instruction: str,
    input_context: str,
    budget_fn: Callable | None = None,
) -> str:
    """Execute one subtask via a single budgeted expert call.

    Returns the expert's output text. Raises ExpertExecutionError on any
    call failure (the scheduler marks the subtask failed, never retries).
    """
    call = budget_fn or chat_budgeted
    prompt = f"{instruction}\n\n{input_context}" if input_context else instruction
    try:
        return call(
            expert_id,
            prompt,
            max_turns=EXECUTOR_MAX_TURNS,
            run_budget=EXECUTOR_RUN_SECONDS,
            toolsets=list(TOOLSET_WHITELIST),
        )
    except Exception as exc:  # noqa: BLE001 — surface as typed error
        raise ExpertExecutionError(f"expert {expert_id} failed: {exc}") from exc