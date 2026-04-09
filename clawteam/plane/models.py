"""Pydantic models for Plane REST API objects."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PlaneWorkspace(BaseModel):
    """Plane workspace (top-level org container)."""

    model_config = {"extra": "ignore"}

    id: str = ""
    name: str = ""
    slug: str = ""


class PlaneProject(BaseModel):
    """Plane project within a workspace."""

    model_config = {"extra": "ignore"}

    id: str = ""
    name: str = ""
    identifier: str = ""
    description: str = ""


class PlaneState(BaseModel):
    """Workflow state in a Plane project."""

    model_config = {"extra": "ignore"}

    id: str = ""
    name: str = ""
    group: str = ""  # "backlog" | "unstarted" | "started" | "completed" | "cancelled"
    color: str = ""
    sequence: float = 0


class PlaneWorkItem(BaseModel):
    """A work item (issue) in Plane."""

    model_config = {"extra": "ignore"}

    id: str = ""
    name: str = ""
    description_html: str = ""
    state: str = ""
    priority: str = "none"
    assignees: list[str] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    sequence_id: int = 0
    project: str = ""


class PlaneComment(BaseModel):
    """A comment on a Plane work item."""

    model_config = {"extra": "ignore"}

    id: str = ""
    comment_html: str = ""
    actor_detail: dict[str, Any] = Field(default_factory=dict)
    created_at: str = ""
