"""Capability registry — extensible string-tagged capabilities for tools.

Public re-exports from `a2kit/__init__.py`: `Cap`, `Capability`, `capabilities`,
`CapabilityRecord`. Internal — leading underscore — registry implementation.

Built-in capabilities:

- `Cap.READ` — auto-applied by `Router.register_read`.
- `Cap.WRITE` — auto-applied by `Router.register_write`.
- `Cap.DESTRUCTIVE`, `Cap.EXPENSIVE`, `Cap.PII`, `Cap.EXTERNAL` — author tags.

Custom caps registered at app startup:

```python
a2kit.capabilities.register("tickets-management", description="...")
```
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Final, TypeAlias

from pydantic import BaseModel, ConfigDict, Field

Capability: TypeAlias = str
"""A capability is a lowercase, hyphen/underscore-allowed string."""

_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]*$")


class Cap(StrEnum):
    """Built-in capability constants — `StrEnum` so values *are* strings.

    Wins over `Final[str]` constants (v0.6 shape):

    - Native autocomplete + iteration: `list(Cap)`.
    - `Cap.WRITE == "write"` is True (StrEnum subclasses `str`).
    - `Cap("write")` parses raw strings — useful for `--select` parsing.
    - Pydantic v2 native serialization.
    """

    READ = "read"
    WRITE = "write"
    DESTRUCTIVE = "destructive"
    EXPENSIVE = "expensive"
    PII = "pii"
    EXTERNAL = "external"


_BUILT_IN: Final[tuple[str, ...]] = tuple(c.value for c in Cap)


class CapabilityRecord(BaseModel):
    """Metadata for a registered capability."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    description: str = ""
    aliases: list[str] = Field(default_factory=list)
    is_built_in: bool = False


class UnknownCapability(ValueError):  # noqa: N818
    """Raised when an unknown atom appears in a select expression / capability lookup."""

    def __init__(self, name: str, *, suggestions: list[str] | None = None) -> None:
        self.name = name
        self.suggestions = list(suggestions or [])
        suffix = f" Did you mean: {', '.join(self.suggestions)}?" if self.suggestions else ""
        super().__init__(f"Unknown capability/atom {name!r}.{suffix}")


class _CapabilitiesNamespace:
    """Public registry namespace (`a2kit.capabilities`)."""

    def __init__(self) -> None:
        self._records: dict[str, CapabilityRecord] = {}
        for cap in Cap:
            self._records[cap.value] = CapabilityRecord(name=cap.value, is_built_in=True)

    def register(self, name: str, *, description: str = "", aliases: list[str] | None = None) -> CapabilityRecord:
        """Register a custom capability. Re-registration with same name is idempotent if metadata matches."""
        if not _NAME_RE.match(name):
            msg = f"Capability name {name!r} must match {_NAME_RE.pattern}"
            raise ValueError(msg)
        record = CapabilityRecord(
            name=name,
            description=description,
            aliases=list(aliases or []),
            is_built_in=name in _BUILT_IN,
        )
        self._records[name] = record
        return record

    def get(self, name: str) -> CapabilityRecord | None:
        """Return record for `name`, or None."""
        return self._records.get(name)

    def all(self) -> dict[str, CapabilityRecord]:
        """Snapshot of registry."""
        return dict(self._records)

    def is_built_in(self, name: str) -> bool:
        """True if `name` is a built-in capability."""
        return name in _BUILT_IN

    def known(self) -> set[str]:
        """All known capability names (built-ins + custom)."""
        return set(self._records)


capabilities = _CapabilitiesNamespace()
"""Module-global capabilities registry. Public as `a2kit.capabilities`."""


__all__ = [
    "Cap",
    "Capability",
    "CapabilityRecord",
    "UnknownCapability",
    "capabilities",
]
