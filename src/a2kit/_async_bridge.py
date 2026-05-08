"""Internal helper: drain an async coroutine to completion from sync code.

Both `tools.py` (for sync tools that need to drive the async store) and
`enrichers.py` (for sync wrappers handling async enricher returns) need the
same 3-tier escape hatch. This module is the single source of truth.

Why a thunk instead of a coroutine:
    A coroutine is single-use — once awaited (or even partially scheduled), it
    cannot be re-driven. The 3-tier strategy may call into anyio more than
    once if the first tier raises after touching the awaitable. A thunk
    (`Callable[[], Awaitable]`) lets each tier mint a fresh coroutine.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


def drain_async_to_sync(make_coro: Callable[[], Awaitable[Any]]) -> Any:
    """Run `make_coro()` to completion from any sync context.

    Tier 1 — `anyio.from_thread.run`: valid when this sync code is a worker
    thread under an async host (e.g. FastMCP's stdio loop, or anything that
    reached us via `anyio.to_thread.run_sync`). Hops the coroutine back to
    the host loop.

    Tier 2 — `anyio.run`: valid when no event loop is in scope on any thread
    we can see (CLI scripts, plain unit tests).

    Tier 3 — fresh worker thread + `anyio.run`: the rare case where a loop
    is running on *this* thread (e.g. an async test that calls a sync
    function which internally needs the async path). Spawning a worker
    thread escapes the running-loop constraint.
    """
    import anyio  # noqa: PLC0415
    import anyio.from_thread  # noqa: PLC0415

    async def _run() -> Any:
        return await make_coro()

    try:
        return anyio.from_thread.run(_run)
    except RuntimeError:
        pass
    try:
        return anyio.run(_run)
    except RuntimeError:
        import concurrent.futures  # noqa: PLC0415

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(anyio.run, _run).result()


__all__ = ["drain_async_to_sync"]
