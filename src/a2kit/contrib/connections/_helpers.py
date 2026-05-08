"""Connection-aware helpers — public re-exports for contrib consumers.

Thin re-export layer for the implementations in `a2kit.tools._connection`.
The originals stay private (underscore-prefixed) because the v0.19 tool
decorator and contrib factories still import them from there;
`get_conn_factory` and any third-party `Depends` factory should pull the
public names from this module instead.
"""

from __future__ import annotations

from a2kit.tools._connection import (
    _lookup_connection_async,
    _resolve_connection_key,
    _resolve_info_strings,
)

lookup_connection_async = _lookup_connection_async
resolve_connection_key = _resolve_connection_key
resolve_info_strings = _resolve_info_strings


__all__ = [
    "lookup_connection_async",
    "resolve_connection_key",
    "resolve_info_strings",
]
