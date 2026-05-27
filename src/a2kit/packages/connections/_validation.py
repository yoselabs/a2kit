"""Connection-key validation primitives.

Shared by ``packages.connections.config`` (the BaseSettings layer) and
``packages.connections.store`` (the disk-IO layer). R8 from the
2026-05-27 structural audit collapsed two `_validate_key` definitions
(one in config, one a thin lazy-import wrapper in store) into this
canonical home — no cycle to break, no wrapper, single source of truth.

Stdlib + a2kit.packages.connections.exceptions only; no further deps.
"""

from __future__ import annotations

import re

from a2kit.packages.connections.exceptions import InvalidConnectionKey

_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def validate_key_part(part: str) -> str:
    """Validate a single connection-key segment; raise InvalidConnectionKey on miss."""
    if not _NAME_RE.match(part):
        raise InvalidConnectionKey(part)
    return part


def validate_key(key: tuple[str, ...]) -> tuple[str, ...]:
    """Validate every segment of ``key``; raise InvalidConnectionKey on empty or bad segment."""
    if not key:
        raise InvalidConnectionKey("")
    for part in key:
        validate_key_part(part)
    return key


__all__ = ["validate_key", "validate_key_part"]
