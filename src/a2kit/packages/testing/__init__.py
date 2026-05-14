"""Testing helpers for a2kit v1 — thin syrupy/vcrpy adoption.

Public API:
  - :func:`cassette` — pytest fixture, vcrpy wrapper.
  - :func:`app` — pytest fixture, fresh :class:`a2kit.App`.
  - :class:`SchemaSnapshotMismatch` — raised on snapshot drift.
  - :func:`compute_schema` — extract a tool's schema dict.
  - :func:`peek` — synchronous container peek (test-only).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from a2kit.packages.testing.exceptions import SchemaSnapshotMismatch
from a2kit.packages.testing.fixtures import app, cassette
from a2kit.packages.testing.null_context import null_context
from a2kit.packages.testing.snapshots import compute_schema

if TYPE_CHECKING:
    from a2kit.app import App


def peek(app_: App, type_: type) -> Any:
    """Test-only sync container peek over :meth:`Container.get`.

    Production code resolves via :meth:`Container.get` during dispatch.
    ``peek`` exists to give a discoverable name for the assertion pattern
    in synchronous tests::

        state = a2kit.testing.peek(app, AppState)
        assert state.config.foo == "bar"

    Driven by ``asyncio.run`` over ``Container.get`` — works from sync test
    bodies. For async tests, call ``await app.container().get(T)`` directly.
    """
    import asyncio

    container = app_.container()
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # No loop running — drive Container.get via asyncio.run.
        return asyncio.run(container.get(type_))
    # Inside an async test: read the app-scope cache directly. Async tests
    # should `await container.get(T)` if the instance isn't already built;
    # peek's role from inside a loop is to inspect already-resolved state
    # (the common case being post-`override`).
    cached = container._singletons.get(type_)  # noqa: SLF001 -- test seam
    if cached is None:
        msg = (
            f"peek({type_!r}) called from inside an event loop with no cached "
            f"app-scope instance. Use `await app.container().get({type_.__name__})` "
            "in async tests instead."
        )
        raise LookupError(msg)
    return cached


__all__ = [
    "SchemaSnapshotMismatch",
    "app",
    "cassette",
    "compute_schema",
    "null_context",
    "peek",
]
