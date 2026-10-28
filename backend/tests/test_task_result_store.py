"""Tests for the task result store (completion marks + result paths)."""

import json

import pytest

from app.task_result_store import TaskResultStore


def test_mark_and_retrieve(tmp_path, monkeypatch):
    p = tmp_path / "task_results.json"
    monkeypatch.setattr("app.task_result_store.RESULTS_PATH", p)
    store = TaskResultStore()
    store.mark_done("t_1", result_path="/ws/t_1.md", summary="完成")
    assert store.is_done("t_1") is True
    r = store.get_result("t_1")
    assert r["result_path"] == "/ws/t_1.md"
    assert r["summary"] == "完成"


def test_missing_file_not_done(tmp_path, monkeypatch):
    p = tmp_path / "task_results.json"
    monkeypatch.setattr("app.task_result_store.RESULTS_PATH", p)
    store = TaskResultStore()
    assert store.is_done("t_nope") is False
    assert store.get_result("t_nope") is None


def test_persists_across_instances(tmp_path, monkeypatch):
    p = tmp_path / "task_results.json"
    monkeypatch.setattr("app.task_result_store.RESULTS_PATH", p)
    TaskResultStore().mark_done("t_a", result_path="/x.md", summary="s")
    store2 = TaskResultStore()
    assert store2.is_done("t_a") is True


def test_load_tolerates_corrupt(tmp_path, monkeypatch):
    p = tmp_path / "task_results.json"
    p.write_text("{corrupt json", encoding="utf-8")
    monkeypatch.setattr("app.task_result_store.RESULTS_PATH", p)
    store = TaskResultStore()
    assert store.is_done("t_1") is False