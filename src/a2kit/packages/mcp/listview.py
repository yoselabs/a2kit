"""List-view middleware — projects fields and paginates list-shaped results.

Reads :class:`a2kit.metadata.ListViewSettings` (attached by the consolidated
``@a2kit.list_(...)`` decorator) from the registered tool's
``meta["a2kit"]["extras"]["list_view"]`` payload. If the tool author
declared ``default_fields`` and the result is a list of dicts, project each
row down to those keys. If ``page_size`` is set, slice. Single objects,
scalars, and non-list results pass through untouched.

Settings are consulted via the FastMCP server registry (looked up by tool
name on the request); the wire payload of ``tool.meta`` is the source of
truth, so it round-trips identically to what middleware reads here.
"""

from __future__ import annotations

import logging
from typing import Any

from fastmcp.server.middleware import Middleware, MiddlewareContext

_log = logging.getLogger(__name__)
_WARN_ONCE: set[str] = set()


def _list_view_settings(meta_a2kit: dict[str, Any]) -> dict[str, Any] | None:
    extras = meta_a2kit.get("extras") if isinstance(meta_a2kit, dict) else None
    lv = extras.get("list_view") if isinstance(extras, dict) else None
    if not lv:
        return None
    return lv if isinstance(lv, dict) else None


def _project_row(row: Any, fields: tuple[str, ...]) -> Any:
    if not isinstance(row, dict):
        return row
    return {k: row[k] for k in fields if k in row}


def _apply_to_items(items: list[Any], settings: dict[str, Any]) -> list[Any]:
    default_fields = tuple(settings.get("default_fields") or ())
    page_size = settings.get("page_size")
    if default_fields:
        items = [_project_row(r, default_fields) for r in items]
    if isinstance(page_size, int) and page_size > 0:
        items = items[:page_size]
    return items


def _apply(result: Any, settings: dict[str, Any]) -> Any:
    if isinstance(result, list):
        return _apply_to_items(result, settings)
    return result


class ListViewMiddleware(Middleware):
    """Apply per-tool list-view settings to the post-call result."""

    async def on_call_tool(
        self,
        context: MiddlewareContext[Any],
        call_next: Any,
    ) -> Any:
        result = await call_next(context)

        params = context.message
        tool_name = getattr(params, "name", None)
        fastmcp_ctx = getattr(context, "fastmcp_context", None)
        if not tool_name or fastmcp_ctx is None:
            return result

        server = getattr(fastmcp_ctx, "fastmcp", None)
        if server is None:
            return result

        try:
            tool = await server.get_tool(tool_name)
        except Exception as exc:  # middleware must not raise; degrade observably
            key = f"{tool_name}::get_tool"
            if key not in _WARN_ONCE:
                _WARN_ONCE.add(key)
                _log.warning("ListViewMiddleware: server.get_tool failed for %s: %s", tool_name, exc)
            return result

        meta_full = getattr(tool, "meta", None) or {}
        meta_a2kit = meta_full.get("a2kit") if isinstance(meta_full, dict) else None
        if not isinstance(meta_a2kit, dict):
            return result

        settings = _list_view_settings(meta_a2kit)
        if settings is None:
            return result

        structured = getattr(result, "structured_content", None)
        if isinstance(structured, dict) and "result" in structured:
            new_inner = _apply(structured["result"], settings)
            new_structured = {**structured, "result": new_inner}
            try:
                return type(result)(
                    content=result.content,
                    structured_content=new_structured,
                    meta=getattr(result, "meta", None),
                )
            except Exception as exc:  # middleware must not raise; degrade observably
                key = f"{tool_name}::project"
                if key not in _WARN_ONCE:
                    _WARN_ONCE.add(key)
                    _log.warning("ListViewMiddleware: result reconstruction failed for %s: %s", tool_name, exc)
                return result

        return result


__all__ = ["ListViewMiddleware"]
