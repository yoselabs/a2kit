"""Store wrappers — ephemeral merge + scope filter (read-only views)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Generic, TypeVar

from a2kit.packages.connections.config import ConnectionConfig
from a2kit.packages.connections.exceptions import ConnectionNotFound

if TYPE_CHECKING:
    from collections.abc import Mapping

    from a2kit.packages.connections.store import ConnectionStore

C = TypeVar("C", bound=ConnectionConfig)


class EphemeralAwareStore:
    """Store proxy: short-circuits `load()` to an ephemeral dict before delegating to base."""

    def __init__(
        self,
        base: Any,
        ephemeral: Mapping[tuple[str, ...], Any] | None,
    ) -> None:
        self._base = base
        self._ephemeral = dict(ephemeral) if ephemeral else {}

    async def load(self, key: tuple[str, ...]) -> Any:
        if key in self._ephemeral:
            return self._ephemeral[key]
        if self._base is None:
            raise ConnectionNotFound(key)
        return await self._base.load(key)

    async def list_connections(self) -> list[Any]:
        if self._base is not None and hasattr(self._base, "list_connections"):
            base_list = await self._base.list_connections()
        else:
            base_list = []
        existing = {tuple(getattr(info, "key", ())) for info in base_list}
        merged = list(base_list)
        for key, info in self._ephemeral.items():
            if key not in existing:
                merged.append(info)
        return merged


class FilteredStore(Generic[C]):
    """Read-only view of a `ConnectionStore` restricted to keys containing `scope`."""

    def __init__(self, store: ConnectionStore[C], scope: str) -> None:
        self._store = store
        self._scope = scope

    def _matches(self, key: tuple[str, ...]) -> bool:
        return any(self._scope == part for part in key)

    async def load(self, key: tuple[str, ...]) -> C:
        if not self._matches(key):
            raise ConnectionNotFound(key)
        return await self._store.load(key)

    async def list_connections(self) -> list[C]:
        return [info for info in await self._store.list_connections() if self._matches(info.key)]

    @property
    def config_dir(self) -> Any:
        return self._store.config_dir


def scope_filter(store: ConnectionStore[C], scope: str | None) -> Any:
    """Return a read-only filtered view of `store`. `None` scope returns the base store."""
    if scope is None:
        return store
    return FilteredStore(store, scope)


__all__ = ["EphemeralAwareStore", "FilteredStore", "scope_filter"]
