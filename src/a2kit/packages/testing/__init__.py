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
    """Test-only container peek over :meth:`Container.resolve`.

    Production code should resolve via the container during dispatch (the
    request-scoped DI surface). ``peek`` exists to give a discoverable name
    for the assertion pattern in tests:

        state = a2kit.testing.peek(app, AppState)
        assert state.config.foo == "bar"

    Resolution is synchronous in v0.27+. Async resource opens belong inside
    resource classes (lazy-init pattern), not in DI factories.
    """
    return app_.container().resolve(type_)


__all__ = [
    "SchemaSnapshotMismatch",
    "app",
    "cassette",
    "compute_schema",
    "null_context",
    "peek",
]
