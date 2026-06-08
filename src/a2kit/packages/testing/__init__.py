"""Testing helpers for a2kit v1 — thin syrupy/vcrpy adoption.

Public API:
  - :func:`cassette` — pytest fixture, vcrpy wrapper.
  - :func:`app` — pytest fixture, fresh :class:`a2kit.App`.
  - :class:`SchemaSnapshotMismatch` — raised on snapshot drift.
  - :func:`compute_schema` — extract a tool's schema dict.
  - :func:`peek` — synchronous container peek (test-only).
  - :func:`resolve` — async DI resolution seam (test-only).
  - :func:`lazy` — wrap a value as a :data:`a2kit.packages.di.Lazy` thunk.

The DI seams (``lazy`` / ``peek`` / ``resolve``) live in
:mod:`a2kit.packages.testing.seams`; the rest in their own submodules.
"""

from __future__ import annotations

from a2kit.packages.testing.exceptions import SchemaSnapshotMismatch
from a2kit.packages.testing.fixtures import (
    ambient_for_tests,
    ambient_for_tests_autouse,
    app,
    app_of,
    cassette,
)
from a2kit.packages.testing.null_context import null_context
from a2kit.packages.testing.seams import lazy, peek, resolve
from a2kit.packages.testing.snapshots import compute_schema

__all__ = [
    "SchemaSnapshotMismatch",
    "ambient_for_tests",
    "ambient_for_tests_autouse",
    "app",
    "app_of",
    "cassette",
    "compute_schema",
    "lazy",
    "null_context",
    "peek",
    "resolve",
]
