"""Expert (Hermes Profile) CRUD routes.

An expert IS a Hermes profile: its identity lives in the profile's
``SOUL.md`` (persona / expertise / prompt sections) and its skills live
in the profile's ``skills/`` directory.
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Response
from pydantic import Field

from app.hermes_client import HermesError, profile_create, profile_list, profile_soul_path, run_hermes
from app.schemas import ExpertCreate, ExpertOut, SkillOut

router = APIRouter(prefix="/api")

_SOUL_SECTION_RE = re.compile(
    r"^#+\s+(persona|expertise|prompt)\s*$(.*?)(?=^#+\s+(?:persona|expertise|prompt)\s*$|\Z)",
    re.MULTILINE | re.DOTALL | re.IGNORECASE,
)


def _profile_home() -> Path:
    return Path.home() / ".hermes" / "profiles"


def _skills_root() -> Path:
    return Path.home() / ".hermes" / "skills"


def _slugify(name: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff-]+", "-", name.strip()).strip("-") or "expert"


def _avatar_for(name: str) -> str:
    """Deterministic emoji from the name hash (light touch)."""
    n = sum(ord(c) for c in name)
    return ["🧑‍💻", "🧠", "🔍", "✍️", "🧪", "🛠️", "📊", "🤖"][n % 8]


def _default_avatar() -> str:
    return "🛠️"


def _parse_soul(text: str) -> dict[str, str]:
    """Parse SOUL.md into persona/expertise/prompt sections."""
    out = {"persona": "", "expertise": "", "prompt": ""}
    for match in _SOUL_SECTION_RE.finditer(text):
        key = match.group(1).strip().lower()
        if key in out:
            out[key] = match.group(2).strip()
    return out


def _profile_skills(name: str) -> list[str]:
    skills_dir = _profile_home() / name / "skills"
    if not skills_dir.is_dir():
        return []
    return sorted(p.name for p in skills_dir.iterdir() if p.is_dir())


def _read_expert(profile_name: str, default_model: str = "deepseek-chat") -> ExpertOut | None:
    soul_path = Path(profile_soul_path(profile_name))
    if not soul_path.is_file():
        return None
    sections = _parse_soul(soul_path.read_text(encoding="utf-8"))
    return ExpertOut(
        id=profile_name,
        display_name=sections.get("persona", "").splitlines()[0] if sections["persona"] else profile_name,
        avatar=_avatar_for(profile_name),
        persona=sections["persona"],
        expertise=sections["expertise"],
        prompt=sections["prompt"],
        model=default_model,
        skills=_profile_skills(profile_name),
        status="parked",
    )


@router.get("/experts", response_model=list[ExpertOut])
def list_experts() -> list[ExpertOut]:
    experts = []
    for name in profile_list():
        expert = _read_expert(name)
        if expert is not None:
            experts.append(expert)
    return experts


@router.post("/experts", response_model=ExpertOut, status_code=201)
def create_expert(payload: ExpertCreate) -> ExpertOut:
    profile_name = _slugify(payload.display_name)
    try:
        profile_create(profile_name)
    except HermesError as exc:
        if "exists" in str(exc).lower():
            raise HTTPException(status_code=409, detail=f"专家 {profile_name} 已存在") from exc
        raise HTTPException(status_code=500, detail=f"创建专家失败: {exc}") from exc

    soul_path = Path(profile_soul_path(profile_name))
    soul_path.parent.mkdir(parents=True, exist_ok=True)
    soul_text = (
        f"# Persona\n{payload.persona}\n\n"
        f"# Expertise\n{payload.expertise}\n\n"
        f"# Prompt\n{payload.prompt}\n"
    )
    soul_path.write_text(soul_text, encoding="utf-8")

    # Bind selected skills by copying their SKILL.md into the profile's skills dir.
    if payload.skills:
        for skill in payload.skills:
            src = _skills_root() / skill / "SKILL.md"
            if not src.is_file():
                continue
            dest = _profile_home() / profile_name / "skills" / skill / "SKILL.md"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    return _read_expert(profile_name, default_model=payload.model)


@router.delete("/experts/{name}", response_model=dict)
def delete_expert(name: str) -> dict:
    profile_name = _slugify(name)
    try:
        run_hermes(["profile", "delete", profile_name, "--yes"])
    except HermesError as exc:
        raise HTTPException(status_code=404, detail=f"删除专家失败: {exc}") from exc
    return {"ok": True}


@router.get("/skills", response_model=list[SkillOut])
def list_skills() -> list[SkillOut]:
    skills_root = _skills_root()
    if not skills_root.is_dir():
        return []
    result = []
    for skill_dir in sorted(skills_root.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.is_file():
            continue
        text = skill_file.read_text(encoding="utf-8")
        try:
            name, desc = _parse_skill_frontmatter(text)
        except Exception:
            name, desc = skill_dir.name, ""
        result.append(SkillOut(name=name, description=desc))
    return result


def _parse_skill_frontmatter(text: str) -> tuple[str, str]:
    """Naive frontmatter parser for SKILL.md (---\nname:...\ndescription:...\n---)."""
    name = ""
    description = ""
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].splitlines():
                if line.startswith("name:"):
                    name = line.split(":", 1)[1].strip()
                elif line.startswith("description:"):
                    description = line.split(":", 1)[1].strip()
    return name or "unnamed", description