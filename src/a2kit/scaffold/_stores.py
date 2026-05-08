"""Internal store proxies used by Router and the runner.

`_EphemeralAwareStore` lifts ephemeral-connection handling out of the tool
decorator (v0.8) — the Router merges its `ephemeral` mapping into the base
store so the @tool layer never sees ephemerals as a special case.

`_FilteredStore` + `scope_filter` give the runner a read-only view of a store
restricted to a key-substring scope.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Generic, TypeVar

from a2kit.connections import ConnectionInfo, ConnectionStore
from a2kit.exceptions import ConnectionNotFound

if TYPE_CHECKING:
    from collections.abc import Mapping

C = TypeVar("C", bound=ConnectionInfo)


class _EphemeralAwareStore:
    """Store proxy: short-circuits `.load()` to an ephemeral dict before
    delegating to the base store. v0.10: `list_connections()` is also proxied
    so the auto-wired `connection_enricher` and connection-key schema
    enrichment can list base-store keys + ephemeral keys uniformly.
    """

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
        existing_keys = {tuple(getattr(info, "key", ())) for info in base_list}
        merged = list(base_list)
        for key, info in self._ephemeral.items():
            if key not in existing_keys:
                merged.append(info)
        return merged


class _FilteredStore(Generic[C]):
    """Read-only view of a `ConnectionStore` restricted to a key-substring scope."""

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
    """Return a read-only filtered view of `store`."""
    if scope is None:
        return store
    return _FilteredStore(store, scope)


__all__ = ["_EphemeralAwareStore", "_FilteredStore", "scope_filter"]
