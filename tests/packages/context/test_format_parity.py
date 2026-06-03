"""Invariant: `context.stderr._format_line` (the inlined copy) and
`ldd.wire.format_ldd_line` (the canonical home) produce byte-identical
output. They diverge → operators see two different log shapes for the
same emission.
"""

from __future__ import annotations

import pytest

from a2kit.packages.context.stderr import _format_line as inlined
from a2kit.packages.log.formatter import format_condensed_line as canonical


@pytest.mark.parametrize(
    ("level", "msg", "fields", "elapsed_ms"),
    [
        ("info", "hello", {}, 0),
        ("warning", "long message here", {"k": "v"}, 1234),
        ("error", "x", {"a": 1, "b": "s"}, 99999),
        ("debug", "", {}, 5),
        ("trace", "msg with spaces", {"path": "/foo"}, 42),
    ],
)
def test_inlined_format_matches_canonical_byte_for_byte(level: str, msg: str, fields: dict, elapsed_ms: int) -> None:
    assert inlined(level, msg, fields, elapsed_ms) == canonical(level, msg, fields, elapsed_ms)
