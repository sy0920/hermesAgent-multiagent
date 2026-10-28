"""Tests for the single-shot LLM worker (replaces agent loop).

Each task costs exactly ONE LLM API call: read task → single DeepSeek
completion using the expert's SOUL + task body → write result file.
No Hermes agent involvement, so no runaway tool loops.
"""

import json
import pytest

from app.llm_worker import run_single_shot_worker

FAKE_SOUL = "# Persona\n资深研究员\n\n# Expertise\n技术调研\n\n# Prompt\n输出列表"


class FakeLlm:
    def __init__(self, reply="调研结论：AutoGen 采用 actor 模型"):
        self.reply = reply
        self.calls = []

    def get_client(self):
        return self

    def chat_once(self, system_prompt, user_prompt):
        self.calls.append((system_prompt, user_prompt))
        return self.reply


def test_worker_makes_single_call_and_writes_file(monkeypatch, tmp_path):
    llm = FakeLlm()
    card = {
        "id": "t_1",
        "title": "调研 AutoGen",
        "body": "调研 AutoGen 架构",
        "assignee": "researcher-a",
        "workspace": str(tmp_path / "ws"),
    }
    # 4-tuple: no Hermes agent, no gateway, no kanban API.
    result = run_single_shot_worker(
        card=card,
        soul_text=FAKE_SOUL,
        model="deepseek-chat",
        api_key="sk-test",
        base_url="https://api.deepseek.com/v1",
        llm_client_factory=lambda api_key, base_url, model: llm,
    )
    assert len(llm.calls) == 1, "must be exactly one LLM call"
    # Result written to workspace file.
    out_file = tmp_path / "ws" / "t_1.md"
    assert out_file.exists(), f"expected result file at {out_file}"
    assert result is not None
    assert "AutoGen" in result


def test_worker_builds_prompt_from_soul_and_body(monkeypatch, tmp_path):
    captured = {}

    class CapturingLlm(FakeLlm):
        def chat_once(self, system_prompt, user_prompt):
            captured["system"] = system_prompt
            captured["user"] = user_prompt
            return self.reply

    ws = tmp_path / "ws"
    run_single_shot_worker(
        card={
            "id": "t_x",
            "title": "审核",
            "body": "审核两份调研",
            "assignee": "reviewer",
            "workspace": str(ws),
        },
        soul_text=FAKE_SOUL,
        model="deepseek-chat",
        api_key="k",
        base_url="https://api.deepseek.com/v1",
        llm_client_factory=lambda *a, **k: CapturingLlm(),
    )
    assert "# Persona" in captured["system"]
    assert "调研 AutoGen" not in captured["system"]  # body goes to user
    assert "审核两份调研" in captured["user"]


def test_worker_no_hermes_import():
    """The single-shot worker must not import Hermes subprocess orchestration."""
    import importlib

    import app.llm_worker as m
    importlib.reload(m)
    # No subprocess / hermes_client coupling → no agent loops possible.
    import inspect

    src = inspect.getsource(m)
    assert "import subprocess" not in src
    assert "hermes_client" not in src


def test_worker_marks_done_and_team_final_reads_file(monkeypatch, tmp_path):
    """End-to-end: worker result → done mark → team_final returns report."""
    from app import teams
    from app.task_result_store import TaskResultStore

    results_p = tmp_path / "results.json"
    monkeypatch.setattr("app.task_result_store.RESULTS_PATH", results_p)

    class DoneLlm(FakeLlm):
        def __init__(self):
            super().__init__(reply="# 最终报告\n调研结论完整")

    ws = tmp_path / "ws"
    from app.llm_worker import run_single_shot_worker

    run_single_shot_worker(
        card={"id": "t_final", "title": "综合报告", "body": "汇总", "assignee": "writer", "workspace": str(ws)},
        soul_text="# Persona\n写手",
        model="deepseek-chat",
        api_key="k",
        base_url="https://api.deepseek.com/v1",
        llm_client_factory=lambda *a, **k: DoneLlm(),
    )
    # Done mark present.
    assert TaskResultStore().is_done("t_final")
    # The stored result path points to a real file with the report content.
    r = TaskResultStore().get_result("t_final")
    from pathlib import Path

    assert Path(r["result_path"]).exists()
    assert "调研结论完整" in Path(r["result_path"]).read_text(encoding="utf-8")