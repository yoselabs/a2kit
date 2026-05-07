"""Example: higher-order decorator with `Unpack[ToolKwargs]` (v0.7).

Build a custom Router classmethod factory whose kwargs are type-checked end-to-end.

Run: `uv run python examples/higher_order_decorator.py`
"""

from __future__ import annotations

from typing import Any, Unpack

import a2kit
from a2kit import Cap, ToolKwargs


class MetricsRouter(a2kit.Router):
    """Router with a custom `expensive` decorator factory.

    Uses `Unpack[ToolKwargs]` so callers get full kwarg autocomplete + type
    checking on the underlying `cls.tool(...)` shape.
    """

    @classmethod
    def expensive(cls, **kwargs: Unpack[ToolKwargs]) -> Any:
        """Auto-tag every tool with `Cap.EXPENSIVE`."""
        existing = set(kwargs.get("capabilities", set()) or set())
        kwargs["capabilities"] = existing | {Cap.EXPENSIVE}
        return cls.tool(**kwargs)


@MetricsRouter.expensive()
async def heavy_query(scope: str) -> dict:
    """A query that should run on a stipulated budget."""
    return {"scope": scope, "rows": 0}


def main() -> None:
    print("MetricsRouter._tools:")
    for binding in MetricsRouter._tools:
        print(f"  fn={binding.fn.__name__} caps={sorted(binding.capabilities)}")


if __name__ == "__main__":
    main()
