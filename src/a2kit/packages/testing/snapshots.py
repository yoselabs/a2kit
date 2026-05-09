"""Per-tool schema snapshots.

`compute_schema(fn)` is re-exported from `a2kit.packages.cli.schemas` (its
canonical location). The previous `TOONSnapshotExtension` was removed when
TOON was dropped as a wire format; if you need schema snapshots, use syrupy's
default JSON extension or write a thin subclass calling
`format_response(data, format_hint="json")`.
"""

from __future__ import annotations

from a2kit.packages.cli.schemas import compute_schema

__all__ = ["compute_schema"]
