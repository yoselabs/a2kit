"""Domain models — Pydantic types that double as tool return schemas.

Returning a `BaseModel` (or `list[BaseModel]`) lets a2kit auto-detect the
output format and snapshot the JSON Schema for lint stability.
"""

from __future__ import annotations

from pydantic import BaseModel


class Project(BaseModel):
    """A project — the container for tasks."""

    id: str
    name: str
    archived: bool = False


class Task(BaseModel):
    """A task that lives inside a project."""

    id: str
    project_id: str
    title: str
    done: bool = False
