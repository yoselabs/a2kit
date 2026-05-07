"""Pydantic config models — fail-fast validation for kwargs at decoration time.

All configs are `frozen=True, extra="forbid"` — typos and unknown kwargs surface
with rich Pydantic errors instead of silent TypeErrors at first call.

Public re-exports: `ToolConfig`, `RunnerConfig`, `BudgetConfig`.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from a2kit._capabilities import Capability  # noqa: TC001 — runtime-needed for Pydantic field annotation


class ToolConfig(BaseModel):
    """Captures every kwarg of `@a2kit.tool(...)`.

    Validated at decoration time. Author-supplied capabilities are unioned with
    auto-tagged caps from the active router (if any).
    """

    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)

    server: Any = None
    store: Any = None
    connection_param: str | None = None
    ephemeral: dict[tuple[str, ...], Any] | None = None
    write: bool = False
    streaming: bool = False
    xml_guard: bool = True
    otel: bool = True
    tool_name: str | None = None
    enricher: Any = None
    resolver_registry: Any = None
    capabilities: frozenset[Capability] = Field(default_factory=frozenset)
    cel_filter_param: str | None = None
    fields_param: str | None = None
    cli: str | None = None


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


__all__ = ["BudgetConfig", "RunnerConfig", "ToolConfig"]
