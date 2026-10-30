"""Tests for gateway pre-warming before chat/worker dispatch."""

import pytest

from app.hermes_client import ensure_gateway


@pytest.fixture(autouse=True)
def _clean_gateway_procs():
    from app import hermes_client

    prev = dict(hermes_client._gateway_procs)
    hermes_client._gateway_procs.clear()
    yield
    hermes_client._gateway_procs.clear()
    hermes_client._gateway_procs.update(prev)


class _FakeProc:
    def __init__(self):
        self._code = None  # None = still running
        self.returncode = None

    def poll(self):
        return self._code


def test_ensure_gateway_starts_once(monkeypatch):
    """Gateway is started per profile, and only once."""
    started = []
    monkeypatch.setattr(
        "app.hermes_client.subprocess.Popen",
        lambda *a, **k: started.append(a[0]) or _FakeProc(),
    )
    monkeypatch.setattr("app.hermes_client.time.sleep", lambda s: None)
    ensure_gateway("researcher-a")
    assert len(started) == 1, "first call should spawn once"
    # Second call for the same profile must not re-spawn (gateway alive).
    ensure_gateway("researcher-a")
    assert len(started) == 1


def test_ensure_gateway_detects_dead_process(monkeypatch):
    """A gateway that died is restarted on the next call."""
    procs = []

    def fake_popen(*a, **k):
        p = _FakeProc()
        procs.append(p)
        return p

    monkeypatch.setattr("app.hermes_client.subprocess.Popen", fake_popen)
    monkeypatch.setattr("app.hermes_client.time.sleep", lambda s: None)
    ensure_gateway("writer")
    # Simulate the gateway process dying.
    procs[0]._code = 1
    ensure_gateway("writer")
    assert len(procs) == 2, "dead gateway should be restarted"