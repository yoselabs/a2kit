"""Testing helpers for a2kit v1 — thin syrupy/vcrpy adoption.

Public API:
  - :func:`cassette` — pytest fixture, vcrpy wrapper.
  - :func:`app` — pytest fixture, fresh :class:`a2kit.App`.
  - :class:`SchemaSnapshotMismatch` — raised on snapshot drift.
  - :class:`TOONSnapshotExtension` — syrupy single-file extension writing TOON.
"""

from __future__ import annotations

from a2kit.packages.testing.exceptions import SchemaSnapshotMismatch
from a2kit.packages.testing.fixtures import app, cassette
from a2kit.packages.testing.snapshots import TOONSnapshotExtension, compute_schema

__all__ = [
    "SchemaSnapshotMismatch",
    "TOONSnapshotExtension",
    "app",
    "cassette",
    "compute_schema",
]
