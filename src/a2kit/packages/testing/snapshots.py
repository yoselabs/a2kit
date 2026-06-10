"""Per-tool schema snapshots.

`compute_schema(fn)` is re-exported from `a2kit.schema` (its canonical
location — transport-neutral, no CLI or MCP dependency). For snapshot
assertions, use syrupy's default JSON extension.
"""

from __future__ import annotations

from a2kit.schema import compute_schema

__all__ = ["compute_schema"]
