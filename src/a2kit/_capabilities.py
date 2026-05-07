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
from typing import Final, TypeAlias

from pydantic import BaseModel, ConfigDict, Field

Capability: TypeAlias = str
"""A capability is a lowercase, hyphen/underscore-allowed string."""

_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]*$")


class Cap:
    """Built-in capability constants. Import for IDE autocomplete + ty type-check."""

    READ: Final[Capability] = "read"
    WRITE: Final[Capability] = "write"
    DESTRUCTIVE: Final[Capability] = "destructive"
    EXPENSIVE: Final[Capability] = "expensive"
    PII: Final[Capability] = "pii"
    EXTERNAL: Final[Capability] = "external"


_BUILT_IN: Final[tuple[str, ...]] = (
    Cap.READ,
    Cap.WRITE,
    Cap.DESTRUCTIVE,
    Cap.EXPENSIVE,
    Cap.PII,
    Cap.EXTERNAL,
)


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
        for name in _BUILT_IN:
            self._records[name] = CapabilityRecord(name=name, is_built_in=True)

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
