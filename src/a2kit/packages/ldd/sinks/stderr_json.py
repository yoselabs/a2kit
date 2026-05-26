"""JSON stderr operator sink — one JSON record per line."""

from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from a2kit.packages.ldd.sinks._core import LddEmission


async def stderr_json_sink(emission: LddEmission, /) -> None:
    """Write one JSON-line record for ``emission`` to stderr."""
    record = {
        "kind": emission.kind,
        "name": emission.name,
        "elapsed_ms": emission.elapsed_ms,
        "tool_name": emission.tool_name,
        "payload": emission.payload,
    }
    print(json.dumps(record, separators=(",", ":"), default=str), file=sys.stderr, flush=True)  # noqa: T201


__all__ = ["stderr_json_sink"]
