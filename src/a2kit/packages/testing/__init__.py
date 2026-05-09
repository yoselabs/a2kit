"""Testing helpers for a2kit v1 — thin syrupy/vcrpy adoption.

Public API:
  - :func:`cassette` — pytest fixture, vcrpy wrapper.
  - :func:`app` — pytest fixture, fresh :class:`a2kit.App`.
  - :func:`make_test_app` — rebuild an App with ``Depends`` factories swapped.
  - :class:`SchemaSnapshotMismatch` — raised on snapshot drift.
  - :class:`TOONSnapshotExtension` — syrupy single-file extension writing TOON.

This package deliberately does NOT re-export vcrpy or syrupy symbols. Tests
import those libraries directly when they need primitives beyond the
fixtures.
"""

from __future__ import annotations

from a2kit.packages.testing.exceptions import SchemaSnapshotMismatch
from a2kit.packages.testing.fixtures import app, cassette, make_test_app
from a2kit.packages.testing.snapshots import TOONSnapshotExtension, compute_schema

__all__ = [
    "SchemaSnapshotMismatch",
    "TOONSnapshotExtension",
    "app",
    "cassette",
    "compute_schema",
    "make_test_app",
]
