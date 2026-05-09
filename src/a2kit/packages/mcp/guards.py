"""Tool-call-contamination guard middleware.

Detects accidental tool-call shapes inside string arguments — a model trying
to invoke another tool by passing the ``<parameter name=...>`` envelope as a
plain string. Raise :class:`ToolCallContamination` so the agent sees a
crisp, actionable error.
"""

from __future__ import annotations

from typing import Any

from fastmcp.server.middleware import Middleware, MiddlewareContext

from a2kit.exceptions import ToolCallContamination

_TOOL_CALL_CONTAMINATION_MARKER = "<parameter name="


def _scan_arguments(arguments: dict[str, Any], tool_name: str) -> None:
    for name, value in arguments.items():
        if isinstance(value, str) and _TOOL_CALL_CONTAMINATION_MARKER in value:
            raise ToolCallContamination(param_name=name, tool_name=tool_name)


class GuardsMiddleware(Middleware):
    """Inspect ``CallToolRequestParams.arguments`` before the call proceeds."""

    async def on_call_tool(
        self,
        context: MiddlewareContext[Any],
        call_next: Any,
    ) -> Any:
        params = context.message
        arguments = getattr(params, "arguments", None) or {}
        tool_name = getattr(params, "name", "") or ""
        _scan_arguments(arguments, tool_name)
        return await call_next(context)


__all__ = ["GuardsMiddleware"]
