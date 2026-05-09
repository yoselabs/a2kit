"""``build_mcp_server(app, **fastmcp_kwargs) -> FastMCP``.

Forwards ``**fastmcp_kwargs`` to ``FastMCP.__init__`` so users can plug in
auth providers, lifespans, transforms, etc., without a2kit owning an
abstraction. Walks ``app.tools()`` and registers each as a ``FunctionTool``;
``A2KitMeta`` round-trips into ``tool.meta["a2kit"]`` for middleware to read.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastmcp import FastMCP
from fastmcp.tools import FunctionTool

from a2kit.metadata import A2KitMeta, get_meta
from a2kit.packages.enrichers import wrap as enricher_wrap
from a2kit.packages.mcp.context import bind_context
from a2kit.packages.mcp.guards import GuardsMiddleware
from a2kit.packages.mcp.listview import ListViewMiddleware


def _meta_to_dict(meta: A2KitMeta) -> dict[str, Any]:
    """JSON-serializable projection of ``A2KitMeta`` for ``tool.meta`` wire output."""
    d = asdict(meta)
    d["tags"] = sorted(meta.tags)
    annotations = d.get("annotations")
    if annotations is not None and hasattr(meta.annotations, "model_dump"):
        d["annotations"] = meta.annotations.model_dump(exclude_none=True)
    d.pop("enricher", None)
    return d


def build_mcp_server(app: Any, **fastmcp_kwargs: Any) -> FastMCP:
    """Build a FastMCP server from an ``a2kit.App``.

    All ``fastmcp_kwargs`` flow straight to ``FastMCP.__init__`` — auth,
    providers, transforms, lifespan, tasks, sampling_handler, etc. a2kit owns
    no auth abstraction; FastMCP plugins work directly.
    """
    server = FastMCP(name=app.name, **fastmcp_kwargs)

    for fn in app.tools():
        meta = get_meta(fn)
        if meta is None:
            continue

        wrapped = enricher_wrap(fn, meta.enricher)
        if meta.context_param_name:
            wrapped = bind_context(wrapped, meta.context_param_name)

        tool = FunctionTool.from_function(
            wrapped,
            name=meta.tool_name,
            tags=set(meta.tags),
            annotations=meta.annotations,
            meta={"a2kit": _meta_to_dict(meta)},
        )
        server.add_tool(tool)

    server.add_middleware(ListViewMiddleware())
    server.add_middleware(GuardsMiddleware())
    return server


__all__ = ["build_mcp_server"]
