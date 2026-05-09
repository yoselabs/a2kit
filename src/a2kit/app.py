from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar

from a2kit.packages.connections.config import ConnectionConfig
from a2kit.routers import Router, RouterRegistry

if TYPE_CHECKING:
    from collections.abc import Callable

ConnT = TypeVar("ConnT", bound=ConnectionConfig)


class App:
    def __init__(self, name: str) -> None:
        self.name = name
        self._routers = RouterRegistry()
        self._connection_types: list[type] = []
        self._stores: dict[type, Any] = {}
        self._factories: dict[Callable[..., Any], Callable[..., Any]] = {}

    def use_factory(self, factory: Callable[..., Any], *, as_: Callable[..., Any]) -> App:
        """Bind ``factory`` under the stable callable identity ``as_``.

        Tools declaring ``Depends(as_)`` resolve through ``factory`` at
        invocation. Replaces the legacy "module-level mutable slot" pattern.
        """
        self._factories[as_] = factory
        return self

    def factories(self) -> dict[Callable[..., Any], Callable[..., Any]]:
        return dict(self._factories)

    def use(self, router: Router) -> App:
        self._routers.add(router)
        return self

    def connect(self, conn_type: type[ConnT]) -> App:
        if conn_type not in self._connection_types:
            self._connection_types.append(conn_type)
        return self

    def get_store(self, conn_type: type[ConnT]) -> Any:
        if conn_type not in self._stores:
            from a2kit.packages.connections import ConnectionStore

            self._stores[conn_type] = ConnectionStore(conn_type)
        return self._stores[conn_type]

    def routers(self) -> list[Router]:
        return self._routers.all()

    def tools(self) -> list[Callable[..., Any]]:
        from a2kit.signature import rebuild_with_factories

        raw = self._routers.tools()
        if not self._factories:
            return raw
        return [rebuild_with_factories(fn, self._factories) for fn in raw]

    def connection_types(self) -> list[type]:
        return list(self._connection_types)
