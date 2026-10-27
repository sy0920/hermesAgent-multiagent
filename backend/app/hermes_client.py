"""Thin wrapper around the Hermes CLI driven via subprocess.

All interactions with the Hermes agent happen through the ``hermes``
command so the backend never depends on Hermes' internals. Every JSON
parse tolerates non-JSON warning lines printed by the CLI by scanning
for the first line that starts a JSON document.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

HERMES_BIN = "hermes"
DEFAULT_TIMEOUT = 120
WORKER_TIMEOUT = 600


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
    data = _parse_json(run_hermes(args))
    if not isinstance(data, dict) or "id" not in data:
        raise HermesError(f"kanban create returned no id: {data!r}")
    return data["id"]


def kanban_list() -> list[dict]:
    """Return all kanban tasks as a list of dicts."""
    data = _parse_json(run_hermes(["kanban", "list", "--json"]))
    if not isinstance(data, list):
        raise HermesError(f"kanban list returned non-list: {data!r}")
    return data


def kanban_show(task_id: str) -> dict:
    """Return details for a single task."""
    data = _parse_json(run_hermes(["kanban", "show", task_id, "--json"]))
    if not isinstance(data, dict):
        raise HermesError(f"kanban show returned non-dict: {data!r}")
    return data


def kanban_unblock(task_id: str) -> None:
    run_hermes(["kanban", "unblock", task_id])


def execute_kanban_task(profile: str, task_id: str, timeout: int = WORKER_TIMEOUT) -> str:
    """Manually dispatch a worker: run the expert profile against a task."""
    return run_hermes(
        ["-p", profile, "chat", "-q", f"work kanban task {task_id}"],
        timeout=timeout,
    )


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