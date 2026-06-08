"""Lazy-init resource pattern demo — v0.27 canonical shape.

DI factories must be synchronous in v0.27. For resources that need an event
loop to open (sqlite connections, browser pools, async HTTP clients), wrap
the resource in a class that opens itself on first call under an internal
lock. AppState holds resource handles as **non-Optional** fields; locks
live inside the resources, not on the state.

The pattern:

- Resource class with sync ``__init__`` (no I/O).
- ``_lock: asyncio.Lock`` field — created on first ``_ensure``, lives forever.
- ``async def _ensure(self) -> Handle`` — opens the underlying connection
  under the lock if not yet open.
- Async business methods that await ``_ensure`` internally.
- Idempotent ``async def close(self)`` — called from the App lifespan's
  shutdown branch (the body after ``yield``).

Run::

    python -m examples.resource_pattern.server fakeshop tick
    python -m examples.resource_pattern.server fakeshop tick --include-history
    python -m examples.resource_pattern.server serve         # MCP transport
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from pydantic import BaseModel

import a2kit

# --------------------------------------------------------------------- #
# Resource class — encapsulates async open + close, lazy on first call.
# --------------------------------------------------------------------- #


class FakeShopCounter:
    """Stand-in for an async resource (e.g. aiosqlite.Connection).

    The "open" is a small async sleep so you can observe the first-call
    cost in the LDD output. Subsequent calls reuse the opened state.
    """

    def __init__(self, initial: int = 0) -> None:
        self._count = initial
        self._handle: dict | None = None  # opened lazily; never Optional on AppState
        self._lock = asyncio.Lock()  # internal — never leaks to state

    async def _ensure(self) -> dict:
        if self._handle is not None:
            return self._handle
        async with self._lock:
            if self._handle is None:
                # Simulate async work (file open, network connect, etc.).
                await asyncio.sleep(0.005)
                self._handle = {"opened_at_count": self._count, "history": []}
            return self._handle

    async def tick(self) -> int:
        handle = await self._ensure()
        self._count += 1
        handle["history"].append(self._count)
        return self._count

    async def history(self) -> list[int]:
        handle = await self._ensure()
        return list(handle["history"])

    async def close(self) -> None:
        if self._handle is not None:
            self._handle["history"].clear()
            self._handle = None


# --------------------------------------------------------------------- #
# AppState — non-Optional resource fields. No locks here.
# --------------------------------------------------------------------- #


@dataclass(slots=True)
class AppState:
    counter: FakeShopCounter = field(default_factory=FakeShopCounter)


def build_state() -> AppState:
    """Sync factory — DI requires sync. Async opens happen on first use."""
    return AppState()


# --------------------------------------------------------------------- #
# Tool surface — receives state via DI; no Optional, no None-guards.
# --------------------------------------------------------------------- #


class TickResponse(BaseModel):
    count: int
    history: list[int]


class FakeShopRouter(a2kit.Router):
    slug = "fakeshop"

    @a2kit.read()
    async def tick(
        self,
        *,
        state: AppState,
        include_history: bool = False,
    ) -> TickResponse:
        """Increment the counter; first call lazily opens the resource."""
        count = await state.counter.tick()
        history = await state.counter.history() if include_history else []
        return TickResponse(count=count, history=history)


# --------------------------------------------------------------------- #
# App composition — singleton state with auto-detected close().
# --------------------------------------------------------------------- #
# v0.35: ``AppState`` has no ``__aexit__``/``aclose``/``close``, so the
# framework runs ``state.counter.close()`` via the wrapper class below.


class _ManagedAppState(AppState):
    """Wrapper exposing ``aclose()`` so the framework's lifecycle
    auto-detection cleans up ``state.counter`` at App ``__aexit__``."""

    async def aclose(self) -> None:
        await self.counter.close()


def build_managed_state() -> _ManagedAppState:
    inner = build_state()
    return _ManagedAppState(counter=inner.counter)


class ResourcePatternApp(a2kit.App):
    name = "resource-pattern-demo"
    routers = (FakeShopRouter,)


app = ResourcePatternApp()
app.provide(AppState, build_managed_state)


def main() -> None:
    a2kit.run(app)


if __name__ == "__main__":
    main()
