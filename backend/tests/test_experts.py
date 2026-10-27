"""Tests for the experts (profile) routes.

Calls the route functions directly (sync) because the sandbox blocks
loopback sockets required by TestClient/ASGITransport.
"""

from pathlib import Path

import pytest

from app import experts
from app.hermes_client import HermesError


def _homedir(monkeypatch, tmp_path) -> Path:
    fake_home = tmp_path / "home"
    (fake_home / ".hermes" / "profiles" / "researcher-a").mkdir(parents=True)
    monkeypatch.setattr("app.experts.Path.home", staticmethod(lambda: fake_home))
    monkeypatch.setattr(
        "app.experts._profile_home", lambda: fake_home / ".hermes" / "profiles"
    )
    return fake_home


def test_create_expert_writes_soul_and_calls_profile(monkeypatch, tmp_path):
    fake_home = _homedir(monkeypatch, tmp_path)
    calls = []
    monkeypatch.setattr(
        "app.experts.profile_create", lambda n: calls.append(("create", n))
    )
    monkeypatch.setattr(
        "app.experts.profile_soul_path",
        lambda n: str(fake_home / ".hermes" / "profiles" / n / "SOUL.md"),
    )
    monkeypatch.setattr("app.experts.run_hermes", lambda *a, **k: "")

    from app.schemas import ExpertCreate

    payload = ExpertCreate(
        display_name="文档评审官",
        persona="10年经验后端",
        expertise="评审文档不写代码",
        prompt="输出格式：列表",
        skills=["code-review"],
    )
    expert = experts.create_expert(payload)
    assert expert.id == "文档评审官"
    assert any(c[0] == "create" for c in calls)
    soul = Path(
        fake_home / ".hermes" / "profiles" / "文档评审官" / "SOUL.md"
    ).read_text(encoding="utf-8")
    assert "# Persona" in soul and "10年经验后端" in soul
    assert "评审文档不写代码" in soul


def test_create_duplicate_profile_returns_409(monkeypatch, tmp_path):
    _homedir(monkeypatch, tmp_path)

    def fail_create(n):
        raise HermesError("profile 'x' already exists")

    monkeypatch.setattr("app.experts.profile_create", fail_create)
    monkeypatch.setattr(
        "app.experts.profile_soul_path",
        lambda n: str(tmp_path / n / "SOUL.md"),
    )
    monkeypatch.setattr("app.experts.run_hermes", lambda *a, **k: "")

    from app.schemas import ExpertCreate
    from fastapi import HTTPException

    payload = ExpertCreate(
        display_name="x", persona="p", expertise="e", prompt="t"
    )
    with pytest.raises(HTTPException) as exc_info:
        experts.create_expert(payload)
    assert exc_info.value.status_code == 409


def test_list_experts_maps_profiles(monkeypatch, tmp_path):
    fake_home = _homedir(monkeypatch, tmp_path)
    monkeypatch.setattr("app.experts.profile_list", lambda: ["researcher-a"])
    profiles = fake_home / ".hermes" / "profiles"
    (profiles / "researcher-a").mkdir(parents=True, exist_ok=True)
    (profiles / "researcher-a" / "SOUL.md").write_text(
        "# Persona\n资深研究员\n\n# Expertise\n技术调研\n\n# Prompt\n输出要点列表\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "app.experts.profile_soul_path",
        lambda n: str(profiles / n / "SOUL.md"),
    )
    monkeypatch.setattr("app.experts.run_hermes", lambda *a, **k: "[]")

    result = experts.list_experts()
    names = {e.id for e in result}
    assert names == {"researcher-a"}
    one = next(e for e in result if e.id == "researcher-a")
    assert one.persona == "资深研究员"


def test_skills_endpoint_returns_list(monkeypatch, tmp_path):
    fake_home = _homedir(monkeypatch, tmp_path)
    skills_root = fake_home / ".hermes" / "skills"
    skill_md = skills_root / "code-review" / "SKILL.md"
    skill_md.parent.mkdir(parents=True, exist_ok=True)
    skill_md.write_text(
        "---\nname: code-review\ndescription: 代码评审方法论\n---",
        encoding="utf-8",
    )
    monkeypatch.setattr("app.experts._skills_root", lambda: skills_root)
    result = experts.list_skills()
    assert {"name": "code-review", "description": "代码评审方法论"} in [
        s.model_dump() for s in result
    ]