"""SQLite ledger for the central orchestrator scheduler.

Owns group_session and subtask rows. This is the scheduler's private task
ledger — experts never read or write it directly; only ``engine.py`` and
the API layer use it. (Deliberately separate from Hermes' kanban.db.)
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

DB_PATH = Path.home() / ".hermes" / "scheduler.db"

_lock = threading.RLock()


class SubtaskRow:
    def __init__(
        self,
        subtask_id: str,
        session_id: str,
        round_no: int,
        expert_id: str,
        title: str,
        instruction: str,
        input_context: str,
        deps: list[str],
        status: str,
        output: str = "",
    ):
        self.subtask_id = subtask_id
        self.session_id = session_id
        self.round_no = round_no
        self.expert_id = expert_id
        self.title = title
        self.instruction = instruction
        self.input_context = input_context
        self.deps = deps
        self.status = status
        self.output = output


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    _init(conn)
    return conn


def _init(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            group_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'submitting',
            user_query TEXT NOT NULL,
            round_no INTEGER NOT NULL DEFAULT 1,
            plan_json TEXT NOT NULL DEFAULT '',
            final_report TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS subtasks (
            subtask_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            round_no INTEGER NOT NULL,
            expert_id TEXT NOT NULL,
            title TEXT NOT NULL,
            instruction TEXT NOT NULL,
            input_context TEXT NOT NULL,
            deps TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL DEFAULT 'pending',
            output TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (session_id) REFERENCES sessions(session_id)
        )
        """
    )
    conn.commit()


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    if "deps" in d:
        try:
            d["deps"] = json.loads(d["deps"])
        except (TypeError, ValueError):
            d["deps"] = []
    return d


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


def create_session(session_id: str, group_id: str, user_query: str) -> None:
    with _lock:
        now = _now()
        with _conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO sessions (session_id, group_id, status, user_query, round_no, created_at, updated_at) "
                "VALUES (?, ?, 'submitting', ?, 1, ?, ?)",
                (session_id, group_id, user_query, now, now),
            )
            conn.commit()


def update_session(session_id: str, **fields) -> dict | None:
    with _lock:
        with _conn() as conn:
            allowed = {"status", "plan_json", "final_report", "round_no", "user_query"}
            sets = {k: v for k, v in fields.items() if k in allowed}
            if not sets:
                return None
            sets["updated_at"] = _now()
            cols = ", ".join(f"{k}=?" for k in sets)
            conn.execute(
                f"UPDATE sessions SET {cols} WHERE session_id=?",
                (*sets.values(), session_id),
            )
            conn.commit()
    return get_session(session_id)


def get_session(session_id: str) -> dict | None:
    with _lock:
        with _conn() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE session_id=?", (session_id,)
            ).fetchone()
    return _row_to_dict(row) if row else None


def list_sessions(status: str | None = None) -> list[dict]:
    with _lock:
        with _conn() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM sessions WHERE status=? ORDER BY created_at", (status,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM sessions ORDER BY created_at"
                ).fetchall()
    return [_row_to_dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Subtasks
# ---------------------------------------------------------------------------


def create_subtask(row: SubtaskRow) -> None:
    with _lock:
        with _conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO subtasks "
                "(subtask_id, session_id, round_no, expert_id, title, instruction, input_context, deps, status, output) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    row.subtask_id,
                    row.session_id,
                    row.round_no,
                    row.expert_id,
                    row.title,
                    row.instruction,
                    row.input_context,
                    json.dumps(row.deps),
                    row.status,
                    row.output,
                ),
            )
            conn.commit()


def update_subtask(subtask_id: str, **fields) -> dict | None:
    with _lock:
        with _conn() as conn:
            allowed = {"status", "output", "expert_id"}
            sets = {k: v for k, v in fields.items() if k in allowed}
            if not sets:
                return None
            cols = ", ".join(f"{k}=?" for k in sets)
            conn.execute(
                f"UPDATE subtasks SET {cols} WHERE subtask_id=?",
                (*sets.values(), subtask_id),
            )
            conn.commit()
    return get_subtask(subtask_id)


def get_subtask(subtask_id: str) -> dict | None:
    with _lock:
        with _conn() as conn:
            row = conn.execute(
                "SELECT * FROM subtasks WHERE subtask_id=?", (subtask_id,)
            ).fetchone()
    return _row_to_dict(row) if row else None


def list_subtasks(session_id: str, round_no: int | None = None) -> list[dict]:
    with _lock:
        with _conn() as conn:
            if round_no is not None:
                rows = conn.execute(
                    "SELECT * FROM subtasks WHERE session_id=? AND round_no=?",
                    (session_id, round_no),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM subtasks WHERE session_id=?", (session_id,)
                ).fetchall()
    return [_row_to_dict(r) for r in rows]