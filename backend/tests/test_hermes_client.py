"""Tests for the Hermes CLI client wrapper."""

import pytest

from app.hermes_client import (
    HermesError,
    execute_kanban_task,
    kanban_create,
    kanban_list,
    kanban_show,
    kanban_unblock,
    profile_create,
    profile_list,
    profile_soul_path,
    run_hermes,
)


class _FakeResult:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def _patch(monkeypatch, result):
    monkeypatch.setattr(
        "app.hermes_client.subprocess.run", lambda *a, **k: result
    )


def test_run_hermes_returns_stdout(monkeypatch):
    _patch(monkeypatch, _FakeResult(stdout="hello\n"))
    assert run_hermes(["profile", "list"]) == "hello\n"


def test_run_hermes_raises_on_nonzero_exit(monkeypatch):
    _patch(monkeypatch, _FakeResult(stderr="boom", returncode=2))
    with pytest.raises(HermesError) as exc_info:
        run_hermes(["nope"])
    assert "boom" in str(exc_info.value)


def test_kanban_create_parses_json_id(monkeypatch):
    _patch(monkeypatch, _FakeResult(stdout='{"id": "t_abc123"}'))
    assert kanban_create("调研", assignee="researcher-a") == "t_abc123"


def test_kanban_create_passes_args(monkeypatch):
    captured = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        return _FakeResult(stdout='{"id": "t_x"}')

    monkeypatch.setattr("app.hermes_client.subprocess.run", fake_run)
    kanban_create("调研", assignee="researcher-a", parent_ids=["t_1", "t_2"])
    args = captured["args"][1:]  # strip the leading "hermes" binary
    assert args[:4] == ["kanban", "create", "调研", "--assignee"]
    assert "--parent" in args
    assert "-p" not in args[:3]


def test_kanban_list_tolerates_warning_prefix(monkeypatch):
    _patch(
        monkeypatch,
        _FakeResult(
            stdout=(
                "\u26a0 some warning\n"
                '[{"id": "t_1", "title": "x", "status": "todo", "assignee": "a"}]'
            )
        ),
    )
    tasks = kanban_list()
    assert tasks == [
        {"id": "t_1", "title": "x", "status": "todo", "assignee": "a"}
    ]


def test_kanban_list_json_parse_failure_raises(monkeypatch):
    _patch(monkeypatch, _FakeResult(stdout="not json"))
    with pytest.raises(HermesError, match="failed to parse"):
        kanban_list()


def test_kanban_show_returns_dict(monkeypatch):
    _patch(monkeypatch, _FakeResult(stdout='{"id": "t_1", "summary": "s"}'))
    assert kanban_show("t_1") == {"id": "t_1", "summary": "s"}


def test_kanban_unblock_calls_cli(monkeypatch):
    _patch(monkeypatch, _FakeResult(stdout="ok"))
    assert kanban_unblock("t_1") is None


def test_execute_kanban_task_runs_expert(monkeypatch):
    captured = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        return _FakeResult(stdout="work done")

    monkeypatch.setattr("app.hermes_client.subprocess.run", fake_run)
    result = execute_kanban_task("researcher-a", "t_1")
    assert result == "work done"
    args = captured["args"][1:]  # strip the leading "hermes" binary
    assert args[:2] == ["-p", "researcher-a"]


def test_profile_create_and_list(monkeypatch):
    _patch(monkeypatch, _FakeResult(stdout="profile 'p' created"))
    assert profile_create("p") is None
    _patch(monkeypatch, _FakeResult(stdout="p\nq\n"))
    assert profile_list() == ["p", "q"]


def test_profile_soul_path():
    path = profile_soul_path("p")
    normalized = path.replace("\\", "/")
    assert normalized.endswith(".hermes/profiles/p/SOUL.md")