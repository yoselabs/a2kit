"""Spike A3: can monty resolve `call_tool` return types via @overload + Literal?

CodeMode exposes one generic `call_tool(name, params) -> Any`. `Any`
defeats the type checker. If monty resolves `@overload` keyed on a
`Literal` tool name, a2kit can generate per-tool overload stubs and the
checker will know `await call_tool("list_tasks", {})` is a `PageDC` —
making typo/wrong-field rejection work without the model annotating.

Run: uv run python scripts/spike_monty_overload.py
"""

from __future__ import annotations

import pydantic_monty

STUBS = """
from dataclasses import dataclass
from typing import Any, Literal, overload

@dataclass
class TaskDC:
    id: int
    title: str
    status: str

@dataclass
class PageDC:
    items: list[TaskDC]
    next_cursor: str | None

@overload
async def call_tool(name: Literal["list_tasks"], params: dict) -> PageDC: ...
@overload
async def call_tool(name: Literal["count"], params: dict) -> int: ...
async def call_tool(name: str, params: dict) -> Any: ...
"""


def check(label: str, code: str) -> None:
    try:
        pydantic_monty.Monty(code, type_check=True, type_check_stubs=STUBS)
    except pydantic_monty.MontyTypingError as exc:
        print(f"  {label:50s} REJECTED -> {str(exc).replace(chr(10), ' ')[:100]}")
    except Exception as exc:
        print(f"  {label:50s} OTHER({type(exc).__name__}) -> {str(exc)[:80]}")
    else:
        print(f"  {label:50s} ACCEPTED")


print("monty @overload + Literal resolution spike —", pydantic_monty.__version__)
print()
# If overloads resolve: line 1 ok, line 2 rejected (PageDC has no `.titel`).
check(
    "overload resolves: p.items ok",
    'p = await call_tool("list_tasks", {})\np.items',
)
check(
    "overload resolves: p.titel rejected",
    'p = await call_tool("list_tasks", {})\np.titel',
)
check(
    "overload resolves: int has no .items",
    'n = await call_tool("count", {})\nn.items',
)
check(
    "unknown tool name falls to -> Any",
    'x = await call_tool("mystery", {})\nx.whatever',
)
print("\ndone.")
