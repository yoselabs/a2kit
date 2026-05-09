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
        # LDD kill-switch: env A2KIT_LDD=off disables both channels at startup.
        # set_ldd(...) and CLI --no-reports/--no-events override per-invocation.
        import os

        env_off = os.environ.get("A2KIT_LDD", "").lower() == "off"
        self._ldd_reports = not env_off
        self._ldd_events = not env_off

    def set_ldd(self, *, reports: bool | None = None, events: bool | None = None) -> App:
        """Override the LDD kill-switch programmatically. ``None`` keeps current value."""
        if reports is not None:
            self._ldd_reports = reports
        if events is not None:
            self._ldd_events = events
        return self

    @property
    def ldd_reports(self) -> bool:
        return self._ldd_reports

    @property
    def ldd_events(self) -> bool:
        return self._ldd_events

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
        """Register ``conn_type`` for ``Depends(...)`` resolution.

        Stores that wrap this connection declare their binding via
        ``class TrackerStore(a2kit.Store[TrackerConn]):`` (Generic) or
        ``conn_type = TrackerConn`` (class attribute). Either form is
        sufficient — no separate ``store=`` registration is needed.
        """
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
        from a2kit.signature import bind_class_dependencies, rebuild_with_factories

        raw = self._routers.tools()
        # First: rewrite Depends(<class>) defaults to closures that resolve at call time.
        bound = [bind_class_dependencies(fn, self) for fn in raw]
        if not self._factories:
            return bound
        return [rebuild_with_factories(fn, self._factories) for fn in bound]

    def connection_types(self) -> list[type]:
        return list(self._connection_types)
