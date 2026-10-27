"""Pydantic schemas shared across the API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ExpertCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=64)
    persona: str = Field(min_length=1, description="你是谁 + 背景")
    expertise: str = Field(description="擅长领域，做什么/不做什么")
    prompt: str = Field(description="工作流程、输出格式与约束")
    model: str = "deepseek-chat"
    skills: list[str] = Field(default_factory=list)
    avatar: str | None = None


class ExpertOut(BaseModel):
    id: str
    display_name: str
    avatar: str
    persona: str
    expertise: str
    prompt: str
    model: str
    skills: list[str]
    status: str


class SkillOut(BaseModel):
    name: str
    description: str = ""


class KanbanTask(BaseModel):
    id: str
    title: str
    status: str
    assignee: str | None = None
    parents: list[str] = Field(default_factory=list)
    children: list[str] = Field(default_factory=list)


class KanbanTaskDetail(KanbanTask):
    body: str = ""
    summary: str | None = None
    metadata: dict = Field(default_factory=dict)
    runs: list = Field(default_factory=list)


class KanbanRunResult(BaseModel):
    run_id: str
    status: str = "started"


class TeamInvokeRequest(BaseModel):
    request: str = Field(min_length=1)


class TeamOut(BaseModel):
    id: str
    display_name: str
    members: list[str] = Field(default_factory=list)


class TeamFinal(BaseModel):
    report: str | None = None