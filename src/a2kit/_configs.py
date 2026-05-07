"""Pydantic config models — fail-fast validation for kwargs at decoration time.

All configs are `frozen=True, extra="forbid"` — typos and unknown kwargs surface
with rich Pydantic errors instead of silent TypeErrors at first call.

Public re-exports: `RunnerConfig`, `BudgetConfig`. (v0.9: `ToolConfig` removed —
it was never wired to the live decorator path. Authoritative kwarg contract is
`a2kit.ToolKwargs` (TypedDict) at the type-check layer.)
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class RunnerConfig(BaseModel):
    """Captures `MCPRunner` runtime kwargs (parsed from argv)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    select: str | None = None
    http: str | None = None
    register_args: list[str] = Field(default_factory=list)
    scope: str | None = None


class BudgetConfig(BaseModel):
    """Loaded from `[tool.a2kit.budgets]`."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    per_tool: dict[str, int] = Field(default_factory=dict)
    total: int | None = None


__all__ = ["BudgetConfig", "RunnerConfig"]
