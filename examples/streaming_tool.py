"""Example: `streaming=True` decorator on stdio (collected) and HTTP (streamed).

Run: `uv run python examples/streaming_tool.py`
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import a2kit
from a2kit.tools import _set_current_transport

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


async def _produce() -> AsyncIterator[dict]:
    for i in range(3):
        yield {"i": i}


@a2kit.tool(streaming=True)
async def stream_widgets() -> AsyncIterator[dict]:
    """Streaming-aware tool. The decorator inspects the active transport."""
    return _produce()


async def run_stdio() -> None:
    _set_current_transport("stdio")
    out = await stream_widgets()
    print(f"stdio (collected list): {out}")


async def run_http() -> None:
    _set_current_transport("http")
    out = await stream_widgets()
    items = [item async for item in out]
    print(f"http  (yielded through): {items}")
    _set_current_transport(None)


def main() -> None:
    asyncio.run(run_stdio())
    asyncio.run(run_http())


if __name__ == "__main__":
    main()
