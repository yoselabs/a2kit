from __future__ import annotations

import re
from enum import StrEnum
from typing import Final


class Cap(StrEnum):
    READ = "read"
    WRITE = "write"
    DESTRUCTIVE = "destructive"
    EXPENSIVE = "expensive"
    PII = "pii"
    EXTERNAL = "external"


_BUILT_IN: Final[frozenset[str]] = frozenset(c.value for c in Cap)
_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]*$")


class CapabilityRegistry:
    def __init__(self) -> None:
        self._known: set[str] = set(_BUILT_IN)

    def register(self, name: str) -> str:
        if not _NAME_RE.match(name):
            raise ValueError(f"Capability name {name!r} must match {_NAME_RE.pattern}")
        self._known.add(name)
        return name

    def known(self) -> frozenset[str]:
        return frozenset(self._known)

    def is_built_in(self, name: str) -> bool:
        return name in _BUILT_IN


capabilities = CapabilityRegistry()
