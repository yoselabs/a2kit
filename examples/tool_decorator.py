"""Example: stack `@a2kit.tools.tool(...)` with FastMCP's `@server.tool()`.

Demonstrates:
- The decorator stacking order (server.tool outer, a2kit.tools.tool inner).
- Custom error enricher hookup (raises a friendlier exception type).
- The `-> str` rejection (uncomment the marked lines to see it fire).

Run: `uv run python examples/tool_decorator.py`
"""

from __future__ import annotations

import asyncio

from mcp.server.fastmcp import FastMCP

import a2kit


class _MyEnricher:
    def enrich(self, exc: Exception, *, tool_name: str | None = None) -> Exception:
        if isinstance(exc, KeyError):
            return RuntimeError(f"Widget not found: {exc.args[0]} (tool: {tool_name})")
        return exc


def main() -> None:
    server = FastMCP("widgets")
    enricher = _MyEnricher()

    widgets = {"alpha": {"id": "alpha", "color": "red"}}

    @server.tool()
    @a2kit.tools.tool(enricher=enricher)
    async def get_widget(widget_id: str) -> dict:
        """Fetch a widget by id. Returns dict, never str."""
        return widgets[widget_id]

    # OK path
    result = asyncio.run(get_widget("alpha"))
    print(f"OK: {result}")

    # Enriched failure
    try:
        asyncio.run(get_widget("missing"))
    except RuntimeError as exc:
        print(f"Enriched error: {exc}")

    # The decorator refuses `-> str` at decoration time. Uncomment to see:
    # @a2kit.tools.tool()
    # def bad_tool(x: int) -> str:
    #     return str(x)


if __name__ == "__main__":
    main()
