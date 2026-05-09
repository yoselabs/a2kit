"""Domain models — Pydantic types that double as tool return schemas.

Returning a `BaseModel` (or `list[BaseModel]`) lets a2kit auto-detect the
output format and snapshot the JSON Schema for lint stability.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


class Project(BaseModel):
    """A project — the container for tasks."""

    id: str
    name: str
    archived: bool = False


class Task(BaseModel):
    """A task that lives inside a project.

    Carries enough fields to make the listview demo non-trivial:
    ``assignee``, ``priority``, ``created_at`` are projectable / filterable.
    """

    id: str
    project_id: str
    title: str
    done: bool = False
    assignee: str | None = None
    priority: Literal["low", "medium", "high"] = "medium"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class BatchReport(BaseModel):
    """Mid-flight chunk emitted from ``bulk_import_tasks`` via ``ctx.report``.

    Demonstrates the stacked ``@reports(ReportT)`` decorator contract:
    agents receive one of these per processed batch as a typed structured
    payload, not a parsed log line.
    """

    batch: int
    accepted: int
    rejected: int
    project_id: str
