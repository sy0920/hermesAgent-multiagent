"""Persistent team registry backed by ~/.hermes/teams.json.

Teams are created and listed through this store; the MVP supports create +
read only (no edit/delete). The file lives beside kanban.db under the hermes
home so it survives process restarts and travels with the profile data.
"""

from __future__ import annotations

import json
import os
import re
import time
import unicodedata
import uuid
from pathlib import Path

from pydantic import BaseModel, Field


class Team(BaseModel):
    id: str
    display_name: str
    avatar: str = "🧩"
    description: str = ""
    leader: str
    members: list[str] = Field(default_factory=list)
    created_at: str = ""


class TeamCreate(BaseModel):
    display_name: str
    description: str = ""
    leader: str
    members: list[str] = Field(default_factory=list)


TEAMS_PATH = Path.home() / ".hermes" / "teams.json"


def _slugify(name: str) -> str:
    """Hermes-valid team id: ascii lowercase letters/digits/-/_.

    Chinese display names have no ascii mapping -> a timestamped fallback id.
    """
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9_-]+", "-", ascii_name.lower()).strip("-")
    if not slug:
        slug = f"team-{int(time.time())}"
    return slug[:64].rstrip("-")


def _create_avatar(name: str) -> str:
    """Deterministic avatar from the team's name."""
    n = sum(ord(c) for c in name)
    return ["🧩", "🚀", "🛠️", "📊", "🎯", "🤖", "🧠", "👥"][n % 8]


class TeamStore:
    """Read/write the teams.json registry."""

    def __init__(self, path: Path | None = None):
        self._path = path or TEAMS_PATH

    def load(self) -> list[Team]:
        if not self._path.is_file():
            return []
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, ValueError):
            return []
        teams = data.get("teams") if isinstance(data, dict) else None
        if not isinstance(teams, list):
            return []
        return [Team(**t) for t in teams if isinstance(t, dict)]

    def _save(self, teams: list[Team]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {"teams": [t.model_dump() for t in teams]},
            ensure_ascii=False,
            indent=2,
        )
        tmp = self._path.with_suffix(f".{uuid.uuid4().hex[:8]}.json.tmp")
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, self._path)

    def create(self, payload: TeamCreate) -> Team:
        teams = self.load()
        team_id = _slugify(payload.display_name)
        if any(t.id == team_id for t in teams):
            raise ValueError(f"team '{team_id}' already exists")
        team = Team(
            id=team_id,
            display_name=payload.display_name,
            avatar=_create_avatar(payload.display_name),
            description=payload.description,
            leader=payload.leader,
            members=list(payload.members),
            created_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
        )
        self._save([*teams, team])
        return team

    def get(self, team_id: str) -> Team | None:
        for t in self.load():
            if t.id == team_id:
                return t
        return None