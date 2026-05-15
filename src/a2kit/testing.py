"""Public alias for ``a2kit.packages.testing``.

Lets tests import the discoverable surface as ``import a2kit.testing as testing``
or ``from a2kit.testing import peek``. Implementation lives in
``a2kit.packages.testing`` to keep the canonical layout under ``packages/``.
"""

from __future__ import annotations

from a2kit.packages.testing import (
    SchemaSnapshotMismatch,
    ambient_for_tests,
    app,
    cassette,
    compute_schema,
    lazy,
    null_context,
    peek,
    resolve,
)
from a2kit.packages.testing.client import TestClient, client

__all__ = [
    "SchemaSnapshotMismatch",
    "TestClient",
    "ambient_for_tests",
    "app",
    "cassette",
    "client",
    "compute_schema",
    "lazy",
    "null_context",
    "peek",
    "resolve",
]
