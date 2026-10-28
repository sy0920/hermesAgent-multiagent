"""Expert (Hermes Profile) CRUD routes.

An expert IS a Hermes profile: its identity lives in the profile's
``SOUL.md`` (persona / expertise / prompt sections) and its skills live
in the profile's ``skills/`` directory.
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.hermes_client import (
    HermesError,
    expert_chat,
    profile_create,
    profile_list,
    profile_soul_path,
    run_hermes,
)
from app.schemas import ChatRequest, ChatResponse, ExpertCreate, ExpertOut, SkillOut

router = APIRouter(prefix="/api")


def _profile_home() -> Path:
    return Path.home() / ".hermes" / "profiles"


def _skills_root() -> Path:
    return Path.home() / ".hermes" / "skills"


def _slugify(name: str) -> str:
    """Produce a Hermes-valid profile id.

    Hermes requires profile names to match ``[a-z0-9-_]``, starting with a
    letter or digit, up to 64 chars. Chinese display names are stripped to
    an ascii slug; if nothing survives we fall back to a timestamped id.
    """
    import unicodedata

    # Decompose unicode (Chinese → NFKD, but those have no latin mapping) then
    # keep only ascii alnum / underscore / hyphen, lowercase.
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9_-]+", "-", ascii_name.lower()).strip("-")
    if not slug:
        slug = f"expert-{int(__import__('time').time())}"[:64]
    return slug[:64].rstrip("-")


def _avatar_for(name: str) -> str:
    """Deterministic emoji from the name hash (light touch)."""
    n = sum(ord(c) for c in name)
    return ["\U0001F9D1\u200d\U0001F4BB", "\U0001F9E0", "\U0001F50D", "\u270D\ufe0f", "\U0001F9EA", "\U0001F6E0\ufe0f", "\U0001F4CA", "\U0001F916"][n % 8]


_SOUL_SECTION_RE = re.compile(
    r"^#+\s*(Persona|Expertise|Prompt)\s*([：:]\s*[^\n]*)?$",
    re.MULTILINE | re.IGNORECASE,
)


def _parse_soul(text: str) -> dict[str, str]:
    """Parse SOUL.md into persona/expertise/prompt sections.

    Tolerates ``# Persona`` / ``## Persona:`` / ``# Persona：内联`` forms.
    Content runs from the heading line to the next heading.
    """
    lines = text.splitlines()
    current: str | None = None
    sections: dict[str, list[str]] = {"persona": [], "expertise": [], "prompt": []}
    for line in lines:
        m = _SOUL_SECTION_RE.match(line)
        if m:
            current = m.group(1).lower()
            inline = m.group(2)
            if inline:
                value = re.sub(r"^[：:]\s*", "", inline).strip()
                if value:
                    sections[current].append(value)
            continue
        if current is not None and line.strip():
            sections[current].append(line.strip())
    return {k: "\n".join(v).strip() for k, v in sections.items()}


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
    persona_lines = [
        ln for ln in sections.get("persona", "").splitlines() if ln.strip()
    ]
    if len(persona_lines) >= 2:
        # First line is the display name; the remainder is the persona.
        display_name = persona_lines[0].strip()[:40]
        persona = "\n".join(persona_lines[1:]).strip()
    elif persona_lines:
        display_name = persona_lines[0].strip()[:40]
        persona = persona_lines[0].strip()
    else:
        display_name = profile_name
        persona = ""
    status, model = _read_profile_status(profile_name)
    return ExpertOut(
        id=profile_name,
        display_name=display_name,
        avatar=_avatar_for(profile_name),
        persona=persona,
        expertise=sections["expertise"],
        prompt=sections["prompt"],
        model=model or default_model,
        skills=_profile_skills(profile_name),
        status=status,
    )


def _read_profile_status(name: str) -> tuple[str, str]:
    """Read a profile's gateway status and model from `hermes profile list`."""
    try:
        stdout = run_hermes(["profile", "list"])
    except HermesError:
        return ("parked", "deepseek-chat")
    for line in stdout.splitlines():
        if name in line:
            tokens = line.split()
            status = "parked"
            model = "deepseek-chat"
            for tok in tokens:
                if tok in {"running", "parked", "stopped"}:
                    status = tok
                if "deepseek" in tok or "gpt" in tok or "claude" in tok:
                    model = tok
            return (status, model)
    return ("parked", "deepseek-chat")


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
    # Pre-check for duplicates (idempotent, robust against CLI wording).
    existing = set(profile_list())
    if profile_name in existing:
        raise HTTPException(status_code=409, detail=f"专家 {profile_name} 已存在")
    try:
        profile_create(profile_name)
    except HermesError as exc:
        raise HTTPException(status_code=502, detail=f"创建专家失败: {exc}") from exc

    soul_path = Path(profile_soul_path(profile_name))
    soul_path.parent.mkdir(parents=True, exist_ok=True)
    # Persona first line carries the display name so list_experts can show it.
    soul_text = (
        f"# Persona\n{payload.display_name}\n{payload.persona}\n\n"
        f"# Expertise\n{payload.expertise}\n\n"
        f"# Prompt\n{payload.prompt}\n"
    )
    soul_path.write_text(soul_text, encoding="utf-8")

    # Persist model configuration on the profile.
    if payload.model:
        try:
            run_hermes(["-p", profile_name, "model", "set", payload.model])
        except HermesError:
            pass  # model config is best-effort; SOUL.md is the primary identity

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
    if profile_name not in set(profile_list()):
        raise HTTPException(status_code=404, detail=f"专家 {profile_name} 不存在")
    try:
        run_hermes(["profile", "delete", profile_name, "--yes"])
    except HermesError as exc:
        # The profile exists but the CLI call failed: report honestly.
        run_hermes(["profile", "delete", profile_name])
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


def expert_chat_route(expert_id: str, payload: ChatRequest) -> ChatResponse:
    """Chat with an expert profile; session_id enables multi-turn resume."""
    if expert_id not in set(profile_list()):
        raise HTTPException(status_code=404, detail=f"专家 {expert_id} 不存在")
    reply, session_id = expert_chat(
        expert_id, payload.message, session_id=payload.session_id
    )
    # session_id is either the caller's resume id or parsed from CLI output.
    return ChatResponse(reply=reply, session_id=session_id or payload.session_id)


@router.post("/experts/{expert_id}/chat", response_model=ChatResponse)
def api_expert_chat(expert_id: str, payload: ChatRequest):
    return expert_chat_route(expert_id, payload)