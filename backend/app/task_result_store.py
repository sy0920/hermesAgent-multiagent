"""Lightweight record of completed tasks and their result paths.

Hermes' kanban CLI has no "complete" command, so we track task completion
in a small sidecar JSON (``~/.hermes/task_results.json``). The kanban board
view merges these marks to show done tasks, and final reports are read
from the persisted result files rather than kanban metadata.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

RESULTS_PATH = Path.home() / ".hermes" / "task_results.json"

_lock = threading.RLock()


class TaskResultStore:
    def __init__(self, path: Path | None = None):
        self._path = path or RESULTS_PATH

    def _load(self) -> dict:
        if not self._path.is_file():
            return {}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _save(self, data: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(f".{os.getpid()}.json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self._path)

    def mark_done(self, task_id: str, result_path: str, summary: str = "") -> None:
        with _lock:
            data = self._load()
            data[task_id] = {
                "status": "done",
                "result_path": result_path,
                "summary": summary,
            }
            self._save(data)

    def is_done(self, task_id: str) -> bool:
        r = self.get_result(task_id)
        return bool(r and r.get("status") == "done")

    def get_result(self, task_id: str) -> dict | None:
        with _lock:
            return self._load().get(task_id)


def mark_task_done(task_id: str, result_path: str, summary: str = "") -> None:
    TaskResultStore().mark_done(task_id, result_path, summary)


def task_is_done(task_id: str) -> bool:
    return TaskResultStore().is_done(task_id)


def task_result(task_id: str) -> dict | None:
    return TaskResultStore().get_result(task_id)