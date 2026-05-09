"""Per-tool schema snapshots — syrupy single-file extension.

`compute_schema(fn)` is re-exported from `a2kit.packages.cli.schemas` (its
canonical location). `TOONSnapshotExtension` subclasses syrupy's
`SingleFileSnapshotExtension` and serializes any schema dict via
`a2kit.packages.formatter.format_response` forced to TOON, so snapshot
bytes are byte-identical to ``<app> schema --format=toon``.
"""

from __future__ import annotations

from typing import Any

from syrupy.extensions.single_file import SingleFileSnapshotExtension

from a2kit.packages.cli.schemas import compute_schema


class TOONSnapshotExtension(SingleFileSnapshotExtension):
    """Syrupy single-file extension that writes TOON-encoded schemas."""

    _file_extension = "toon"
    file_extension = "toon"

    def serialize(self, data: Any, **kwargs: Any) -> str:
        from a2kit.packages.formatter import format_response

        return format_response(data, format_hint="toon").data


__all__ = ["TOONSnapshotExtension", "compute_schema"]
