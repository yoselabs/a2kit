"""``Connections`` plugin — owns connection registration, CLI, and DI resolvers.

Registered via ``app.use(Connections())``. After registration:

- ``app.use(<ConnectionConfig subclass>)`` is claimed by this plugin.
- ``<app> connections login/logout/list/show/delete`` subcommands appear
  in the CLI.
- ``Depends(<ConnT>)`` and ``Depends(<StoreT>)`` resolve via this
  plugin's resolvers when the App's ``tools()`` are built.

Without ``app.use(Connections())`` the connections feature is dormant —
no CLI subgroup, no DI resolution, and the connections package's
import-time cost is not paid by the core.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from a2kit.packages.connections.config import ConnectionConfig
from a2kit.packages.connections.di import ConnDependsResolver, StoreDependsResolver

if TYPE_CHECKING:
    import click

    from a2kit.app import App
    from a2kit.plugin import DependsResolver


class Connections:
    """Plugin entry point. ``app.use(Connections())`` activates the feature."""

    def __init__(self) -> None:
        self._conn_types: list[type[ConnectionConfig]] = []
        self._stores: dict[type, Any] = {}
        self._app: App | None = None

    def register(self, app: App) -> None:
        self._app = app

    # --- Plugin claim/adopt — handles `app.use(<ConnectionConfig subclass>)` --- #

    def claim(self, thing: Any) -> bool:
        return isinstance(thing, type) and issubclass(thing, ConnectionConfig)

    def adopt(self, thing: type[ConnectionConfig], app: App) -> None:  # noqa: ARG002
        if thing not in self._conn_types:
            self._conn_types.append(thing)

    # --- Plugin contributions ------------------------------------------- #

    def cli_commands(self) -> list[click.Command]:
        from a2kit.packages.connections.cli import connections_group

        return [connections_group]

    def depends_resolvers(self) -> list[DependsResolver]:
        return [ConnDependsResolver(self), StoreDependsResolver(self)]

    # --- Plugin-private state accessors --------------------------------- #

    def conn_types(self) -> list[type[ConnectionConfig]]:
        """Connection classes registered through this plugin."""
        return list(self._conn_types)

    def get_store(self, conn_type: type[ConnectionConfig]) -> Any:
        """Return the cached ``ConnectionStore`` for ``conn_type``.

        Lazy-constructs on first access. Mirrors the legacy
        ``App.get_store(...)`` shape so ``get_conn_factory(...)`` continues
        to work.
        """
        if conn_type not in self._stores:
            from a2kit.packages.connections.store import ConnectionStore

            self._stores[conn_type] = ConnectionStore(conn_type)
        return self._stores[conn_type]


def find_connections(app: App) -> Connections | None:
    """Locate the registered ``Connections`` plugin on ``app`` (or None)."""
    for plugin in app.plugins():
        if isinstance(plugin, Connections):
            return plugin
    return None


__all__ = ["Connections", "find_connections"]
