"""Testing helpers for a2kit v1 — thin syrupy/vcrpy adoption.

Public API:
  - :func:`cassette` — pytest fixture, vcrpy wrapper.
  - :func:`app` — pytest fixture, fresh :class:`a2kit.App`.
  - :class:`SchemaSnapshotMismatch` — raised on snapshot drift.
  - :func:`compute_schema` — extract a tool's schema dict.
"""

from __future__ import annotations

from a2kit.packages.testing.exceptions import SchemaSnapshotMismatch
from a2kit.packages.testing.fixtures import app, cassette
from a2kit.packages.testing.snapshots import compute_schema

__all__ = [
    "SchemaSnapshotMismatch",
    "app",
    "cassette",
    "compute_schema",
]
