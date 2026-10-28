"""Thin wrapper around the Hermes CLI driven via subprocess.

All interactions with the Hermes agent happen through the ``hermes``
command so the backend never depends on Hermes' internals. Every JSON
parse tolerates non-JSON warning lines printed by the CLI by scanning
for the first line that starts a JSON document.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path

HERMES_BIN = os.environ.get("HERMES_BIN", "hermes")
DEFAULT_TIMEOUT = 120
WORKER_TIMEOUT = 600

# Track per-profile gateway processes so we only warm once and can detect
# a died gateway on the next call.
_gateway_procs: dict[str, subprocess.Popen] = {}


def ensure_gateway(profile: str, timeout: float = 3.0) -> None:
    """Make sure the Hermes gateway for ``profile`` is running.

    Hermes' ``chat`` command requires its gateway to be up; the first call
    per profile spawns it (detached) and polls briefly, so subsequent
    ``chat``/worker calls don't hit "Gateway starting: deadline".
    """
    existing = _gateway_procs.get(profile)
    if existing is not None and existing.poll() is None:
        return  # still alive
    args = [HERMES_BIN, "-p", profile, "gateway", "start"]
    try:
        proc = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except (FileNotFoundError, OSError):
        # Gateway warm-up is best-effort; the chat call itself will surface
        # a clearer error if it truly can't start.
        return
    _gateway_procs[profile] = proc
    time.sleep(timeout)


class HermesError(RuntimeError):
    """Raised when the Hermes CLI exits non-zero or emits unparseable output."""


def run_hermes(args: list[str], timeout: int = DEFAULT_TIMEOUT) -> str:
    """Run ``hermes <args>`` and return stdout (stripped trailing newline)."""
    try:
        proc = subprocess.run(
            [HERMES_BIN, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise HermesError(f"hermes timed out after {timeout}s: {args}") from exc
    except FileNotFoundError as exc:
        raise HermesError(
            f"hermes 命令不存在。请在 PATH 中添加 Hermes 可执行文件目录"
            f"（如 HERMES_BIN 或 ~/.local/bin），然后重试"
        ) from exc
    if proc.returncode != 0:
        raise HermesError(proc.stderr.strip() or proc.stdout.strip() or "hermes failed")
    return proc.stdout


def _parse_json(stdout: str) -> list | dict:
    """Extract the JSON document from CLI output, ignoring warning lines."""
    for line in stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if _looks_like_json(stripped):
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                break
    raise HermesError(f"failed to parse JSON from hermes output: {stdout[:200]!r}")


def _looks_like_json(text: str) -> bool:
    return text.startswith(("[", "{")) and text.endswith(("]", "}"))


def _profile_home() -> Path:
    hermes_root = Path.home() / ".hermes"
    return hermes_root / "profiles"


# ---------------------------------------------------------------------------
# Kanban
# ---------------------------------------------------------------------------


def kanban_create(
    title: str,
    *,
    assignee: str,
    parent_ids: list[str] | None = None,
    body: str = "",
    priority: int = 2,
    workspace: str | None = None,
) -> str:
    """Create a kanban task and return its id (``t_...``)."""
    args = ["kanban", "create", title, "--assignee", assignee]
    for pid in parent_ids or []:
        args += ["--parent", pid]
    if body:
        args += ["--body", body]
    args += ["--priority", str(priority), "--json"]
    if workspace:
        args += ["--workspace", workspace]
    try:
        data = _parse_json(run_hermes(args))
    except HermesError:
        # Retry without the --json flag (older Hermes prints a text table).
        retry_args = [a for a in args if a != "--json"]
        text = run_hermes(retry_args)
        match = re.search(r"\bt_([0-9a-f]{4,})\b", text)
        if not match:
            raise HermesError(f"kanban create returned no id: {text[:200]!r}")
        return match.group(0)
    if not isinstance(data, dict) or "id" not in data:
        raise HermesError(f"kanban create returned no id: {data!r}")
    return data["id"]


def kanban_list() -> list[dict]:
    """Return all kanban tasks.

    Prefers ``--json`` output; falls back to parsing the plain-text table
    that Hermes prints when the CLI release predates the flag.
    """
    try:
        json_text = run_hermes(["kanban", "list", "--json"])
        data = _parse_json(json_text)
    except HermesError:
        text = run_hermes(["kanban", "list"])
        data = _parse_kanban_table(text)
        if not data:
            raise HermesError(
                f"kanban list failed (json={json_text[:120]!r}, text={text[:120]!r})"
            )
    if not isinstance(data, list):
        raise HermesError(f"kanban list returned non-list: {data!r}")
    return data


def _parse_kanban_table(text: str) -> list[dict]:
    """Parse the human-facing ``hermes kanban list`` table.

    Hermes prints one row per task: ``<icon> <id> <status> <assignee> <title>``
    where icon may be ▶ ● ◻ ⊘ ✓ and columns are space-separated (no fixed
    widths in `--json`-less mode). We locate the ``t_`` id and treat the
    tokens around it defensively.
    """
    tasks: list[dict] = []
    status_words = {"todo", "ready", "doing", "running", "done", "blocked"}
    icon_tokens = {"\u25b6", "\u25cf", "\u25fb", "\u2298", "\u2713"}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or len(stripped) < 8:
            continue
        tokens = stripped.split()
        id_idx = next(
            (i for i, t in enumerate(tokens) if t.startswith("t_") and len(t) >= 3),
            None,
        )
        if id_idx is None:
            continue
        task_id = tokens[id_idx]
        # Status: either the token right after the id, or derived from icon.
        status = "todo"
        if id_idx + 1 < len(tokens) and tokens[id_idx + 1] in status_words:
            status = tokens[id_idx + 1]
        # Assignee: the token right after status (before the title).
        assignee = None
        title_start = id_idx + 1
        if id_idx + 1 < len(tokens) and tokens[id_idx + 1] in status_words:
            if id_idx + 2 < len(tokens):
                assignee = tokens[id_idx + 2]
                title_start = id_idx + 3
        title = " ".join(tokens[title_start:])
        tasks.append(
            {
                "id": task_id,
                "title": title,
                "status": status,
                "assignee": assignee,
                "parents": [],
            }
        )
    return tasks


def kanban_show(task_id: str) -> dict:
    """Return details for a single task (JSON-first with text fallback)."""
    try:
        data = _parse_json(run_hermes(["kanban", "show", task_id, "--json"]))
    except HermesError:
        # Minimal fallback: the CLI prints a heading plus key: value lines.
        data = _parse_kanban_show_text(run_hermes(["kanban", "show", task_id]))
    if not isinstance(data, dict):
        raise HermesError(f"kanban show returned non-dict: {data!r}")
    return data


def _parse_kanban_show_text(text: str) -> dict:
    """Parse ``hermes kanban show <id>`` plain-text output into a dict."""
    row: dict = {"id": None, "title": "", "status": "todo", "assignee": None,
                 "body": "", "summary": None, "metadata": {}, "runs": [], "parents": []}
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("Task "):
            rest = stripped[len("Task "):]
            parts = rest.split(":", 1)
            if parts[0].startswith("t_"):
                row["id"] = parts[0].strip()
                row["title"] = parts[1].strip() if len(parts) > 1 else ""
        elif stripped.startswith(("status:", "assignee:", "body:", "summary:")):
            key, _, value = stripped.partition(":")
            key = key.strip().lower()
            if key in {"status", "assignee", "body", "summary"}:
                row[key] = value.strip()
    return row


def kanban_unblock(task_id: str) -> None:
    run_hermes(["kanban", "unblock", task_id])


def execute_kanban_task(
    profile: str,
    task_id: str,
    timeout: int = WORKER_TIMEOUT,
    extra_context: str = "",
) -> str:
    """Manually dispatch a worker: run the expert profile against a task.

    The prompt instructs the worker to follow the full kanban worker
    lifecycle: read the task via kanban_show, do the work, then record the
    outcome via kanban_complete with a summary and ``metadata.final`` so
    downstream aggregation (team_final) has something to read.

    ``extra_context`` (e.g. parent-task summaries) is appended to the
    worker prompt so downstream members see upstream outputs.
    """
    ensure_gateway(profile)
    prompt = (
        f"You are the kanban worker for task {task_id}. "
        f"Work the kanban task:\n"
        f"1. Call kanban_show(task_id=\"{task_id}\") to read the task spec.\n"
        f"2. Complete the work described in the task body.\n"
        f"3. Call kanban_complete(task_id=\"{task_id}\", "
        f"summary=\"<工作摘要>\", metadata={{\"final\": \"<最终结果 Markdown>\"}}).\n"
        f"Always record metadata.final with your complete deliverable."
    )
    if extra_context:
        prompt += f"\n\n## 上游上下文\n{extra_context}"
    return run_hermes(
        ["-p", profile, "chat", "-q", prompt],
        timeout=timeout,
    )


def expert_chat(
    profile: str,
    message: str,
    session_id: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> tuple[str, str | None]:
    """Chat with an expert profile; resume a session when session_id given.

    Returns ``(reply, session_id)`` where session_id is parsed from the CLI's
    ``Session:`` line (or echoed back from the caller), so the caller can
    resume the conversation on the next turn.
    """
    ensure_gateway(profile)
    args = ["-p", profile, "chat"]
    if session_id:
        args += ["--resume", session_id]
    args += ["-q", message]
    stdout = run_hermes(args, timeout=timeout)
    lines = stdout.splitlines()

    # Extract the "Session: <id>" line the CLI prints at the end.
    parsed_session = None
    for ln in lines:
        m = re.search(r"(?:Session|session)\s*[::]\s*(\S+)", ln)
        if m:
            parsed_session = m.group(1).strip()
    effective_session = parsed_session or session_id

    reply = _extract_reply(stdout)
    return reply, effective_session


def _extract_reply(stdout: str) -> str:
    """Extract the assistant's reply from raw Hermes CLI output.

    Anchors instead of guessing: the reply begins at the ``☤ Hermes``
    marker line (the CLI's separator before the assistant response) and
    ends at the session-statistics trailer (``hermes --resume`` /
    ``Title:``). Any chain-of-thought printed *before* the marker is
    discarded wholesale, and blank runs are collapsed.
    """
    lines = stdout.splitlines()

    # Find the "☤ Hermes" marker — the start of the assistant reply.
    start = None
    for i, ln in enumerate(lines):
        if "☤ Hermes" in ln:
            start = i + 1
            break
    if start is None:
        # No marker (plain CLI run): fall back to dropping known chatter.
        start = 0

    body: list[str] = []
    for ln in lines[start:]:
        stripped = ln.strip()
        if stripped.startswith(("Title:", "Duration:", "Messages:", "────────────────", "Session:")):
            break  # session-statistics trailer begins
        if stripped.startswith(("Query:", "Resume this session", "hermes --resume", "hermes -c", "Available Tools", "Available Skills", "Welcome to Hermes", "✦ Tip:", "⚠", "Moday:")):
            continue  # chatter lines to skip
        body.append(stripped)

    # Collapse 3+ consecutive blank lines to a single blank separator.
    collapsed: list[str] = []
    blank_run = 0
    for ln in body:
        if ln:
            blank_run = 0
            collapsed.append(ln)
        else:
            blank_run += 1
            if blank_run == 1:
                collapsed.append("")
    return "\n".join(collapsed).strip()


# ---------------------------------------------------------------------------
# Profiles (experts)
# ---------------------------------------------------------------------------


def profile_create(name: str) -> None:
    run_hermes(["profile", "create", name])


def profile_list() -> list[str]:
    """Return profile names; the default profile is included."""
    stdout = run_hermes(["profile", "list"])
    names = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        # `hermes profile list` lines look like "  some-profile    ..."
        token = re.split(r"\s+", line)[0]
        if token and token not in names:
            names.append(token)
    return names


def profile_soul_path(name: str) -> str:
    """Filesystem path of a profile's SOUL.md (may not exist yet)."""
    return str(_profile_home() / name / "SOUL.md")


def profile_config_path(name: str) -> str:
    """Filesystem path of a profile's config.yaml."""
    return str(_profile_home() / name / "config.yaml")