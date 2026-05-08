"""Error enrichment — turn cryptic exceptions into agent-actionable ones.

This module replaces the v0.10 `a2kit.errors` (removed in v0.13). The split
clarifies the library's vocabulary: `a2kit.exceptions` holds exception
*classes*, `a2kit.enrichers` holds the enrichment *functions* that wrap them.

An *enricher* is a function: it takes an exception and an optional tool name,
returns either the same exception (no change) or a new one with more context.
That's the entire contract — there is no Protocol, no Registry, no class
hierarchy. The decorator's `enricher=` kwarg accepts any callable that matches
the shape.

```python
def enrich_columns(exc: Exception, tool_name: str | None = None) -> Exception:
    if not isinstance(exc, ColumnNotFoundError):
        return exc
    return RuntimeError(f"Column not found: {exc.column}; available: …")
```

Compose multiple enrichers with `chain(*fns)` — first transforms wins,
subsequent skip. Authors with one enricher don't need it.

```python
@a2kit.tool(enricher=chain(enrich_columns, connection_enricher(store)))
async def query(...): ...
```

Built-in: `connection_enricher(store)` factory enriches `ConnectionNotFound`
with the saved-keys list and a difflib suggestion. Wraps the store; returns a
plain function — no class to subclass.
"""

from __future__ import annotations

import concurrent.futures
import inspect
from collections.abc import Awaitable, Callable
from difflib import get_close_matches
from typing import TYPE_CHECKING, Any, cast

import anyio
import anyio.from_thread

from a2kit.exceptions import ConnectionNotFound

if TYPE_CHECKING:
    from a2kit.connections import ConnectionStoreLike

EnricherFn = Callable[[Exception, str | None], Exception | Awaitable[Exception]]
"""Type alias: an enricher is `(exc, tool_name) -> exc | Awaitable[exc]`.

v0.11 broadened the contract — enrichers may now return a coroutine. The
async tool wrapper detects the coroutine and awaits it; the sync wrapper
errors loudly if a coroutine is returned (running an event loop just to
enrich an exception would be wrong, and silently dropping the coroutine
would be worse).

Returning the same object (`is exc`) means no enrichment was applied,
identical to v0.10 semantics.
"""


async def apply_enricher_async(
    enricher: EnricherFn,
    exc: Exception,
    tool_name: str | None,
) -> Exception:
    """Internal helper used by the async tool wrapper.

    Calls `enricher`, awaits it if the result is a coroutine, returns the
    enriched exception (or the original — first-transforms-wins applies).
    """
    result: Exception | Awaitable[Exception] = enricher(exc, tool_name)
    if isinstance(result, Exception):
        return result
    return await result


def apply_enricher_sync(
    enricher: EnricherFn,
    exc: Exception,
    tool_name: str | None,
) -> Exception:
    """Internal helper used by the sync tool wrapper.

    Calls `enricher`. If it returned a coroutine (the v0.11 default for the
    built-in `connection_enricher`, since the store is async-first), drains
    it through `anyio` so sync tools keep working without losing the
    enrichment feature:

    - Inside FastMCP's worker-thread sync-tool path → `anyio.from_thread.run`
      hops back to the host loop.
    - Outside any async runtime (CLI / test scripts) → `anyio.run` spins up
      a one-shot loop.
    """
    result: Exception | Awaitable[Exception] = enricher(exc, tool_name)
    if isinstance(result, Exception):
        return result

    # The enricher returned an awaitable; close *this* one (we won't drive it)
    # and mint fresh ones inside the thunk — `drain_async_to_sync` may call
    # the thunk more than once across its 3 tiers, and a coroutine is single-
    # use.
    if inspect.iscoroutine(result):
        result.close()

    async def _coro() -> Exception:
        r = enricher(exc, tool_name)
        if isinstance(r, Exception):
            return r
        return await r

    # 3-tier drain: from_thread.run (worker under host loop) → anyio.run
    # (no loop) → fresh worker thread (loop on this thread). Each tier mints
    # a fresh coroutine via `_coro` since coroutines are single-use.
    drained: Any
    try:
        drained = anyio.from_thread.run(_coro)
    except RuntimeError:
        try:
            drained = anyio.run(_coro)
        # pragma below: 3rd-tier fallback fires only when anyio.run is called from inside a running loop on this thread
        except RuntimeError:  # pragma: no cover
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                drained = ex.submit(anyio.run, _coro).result()
    return cast("Exception", drained)


def chain(*enrichers: EnricherFn) -> EnricherFn:
    """Compose enrichers — first one to transform wins, subsequent skip.

    Empty chain is the identity enricher. The chain itself is sync; if any
    member returns a coroutine, the chain returns the same coroutine
    unchanged (the tool wrapper resolves it).
    """

    def chained(exc: Exception, tool_name: str | None = None) -> Exception | Awaitable[Exception]:
        for fn in enrichers:
            new = fn(exc, tool_name)
            if inspect.isawaitable(new):
                # Hand the awaitable to the wrapper unresolved; we can't compare
                # `is exc` until it's awaited, so we treat any awaitable as
                # "definitely transformed" (which is the right call — an
                # enricher that wants to be async-only is opting in to a
                # transformation, never a passthrough).
                return new  # type: ignore[no-any-return]
            if new is not exc:
                return new
        return exc

    return chained  # type: ignore[return-value]


def connection_enricher(store: ConnectionStoreLike) -> EnricherFn:
    """Enrich `ConnectionNotFound` with available-keys list + difflib suggestion.

    Other exceptions pass through. Closes over the store; returns an `async
    def` enricher because v0.11's `store.list_connections` is async. Sync
    tool wrappers handle the coroutine via `apply_enricher_sync`, which
    drains it through `anyio` so sync callers don't lose the feature.
    """

    async def enrich(exc: Exception, tool_name: str | None = None) -> Exception:
        if not isinstance(exc, ConnectionNotFound):
            return exc
        available = ["-".join(info.key) for info in await store.list_connections()]
        wanted = "-".join(exc.key)
        parts = [f"Connection not found: {wanted}"]
        if available:
            parts.append(f"Available: {', '.join(sorted(available))}")
            close = get_close_matches(wanted, available, n=1, cutoff=0.5)
            if close:
                parts.append(f"Did you mean: {close[0]}?")
        else:
            parts.append("No connections are configured.")
        if tool_name is not None:
            parts.append(f"(while running tool {tool_name!r})")
        new = ConnectionNotFound(exc.key)
        new.args = ("\n".join(parts),)
        new.available_connections = available
        return new

    return enrich  # type: ignore[return-value]


__all__ = ["EnricherFn", "apply_enricher_async", "apply_enricher_sync", "chain", "connection_enricher"]
