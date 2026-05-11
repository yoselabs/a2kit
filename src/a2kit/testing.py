"""Public alias for ``a2kit.packages.testing``.

Lets tests import the discoverable surface as ``import a2kit.testing as testing``
or ``from a2kit.testing import peek``. Implementation lives in
``a2kit.packages.testing`` to keep the canonical layout under ``packages/``.
"""

from __future__ import annotations

from a2kit.packages.testing import (
    SchemaSnapshotMismatch,
    app,
    cassette,
    compute_schema,
    null_context,
    peek,
)
from a2kit.packages.testing.client import TestClient, client

__all__ = [
    "SchemaSnapshotMismatch",
    "TestClient",
    "app",
    "cassette",
    "client",
    "compute_schema",
    "null_context",
    "peek",
]
