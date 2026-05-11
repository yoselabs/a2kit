"""Router factory for connection-type providers.

Pairs with :func:`a2kit.packages.connections.cli.connections_cli`:

.. code-block:: python

    app = a2kit.App("tracker")
    app.add_router(connections(TrackerConn))      # installs the provider honestly
    app.add_cli(connections_cli(TrackerConn))     # adds the CLI subcommands

Previously a single ``app.add_cli(connections_cli(TrackerConn))`` call did
both — the provider install was a hidden side effect of an ``_a2kit_connections_types``
marker on the returned Click group. The new shape makes the two installs
explicit. The marker continues to work for one release with a deprecation
warning; see :func:`a2kit.packages.connections.cli.connections_cli`.

Future: when the connection-CLI subcommands are rewritten as a2kit-decorated
tool methods (so they surface on MCP too, gated by :class:`Surface.CLI` for
the credential-management ones), the returned Router will carry those tools
directly and the separate ``add_cli`` call goes away.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from a2kit.routers import Router

if TYPE_CHECKING:
    from a2kit.app import App
    from a2kit.packages.connections.config import ConnectionConfig


def connections(*conn_types: type[ConnectionConfig]) -> Router:
    """Return a Router that installs typed providers for ``conn_types``.

    The Router carries no tools today — credential-management subcommands
    continue to ship as a Click group via :func:`connections_cli`. Call both
    factories for the full surface.

    The provider plumbing routes through
    :func:`a2kit.packages.connections.container.install_connection_providers`,
    which wires the ``connection`` resolver chain (wire ``connection`` →
    loaded TOML → ``ConnectionConfig`` subclass). The simpler default
    ``app.provide(T)`` path would only handle classes whose ``__init__``
    the container can introspect — connection configs need more.
    """

    class _ConnectionsRouter(Router):
        name = "connections"
        # providers stays empty: install() does the work below.

        def install(self, app: App) -> Any:
            from a2kit.packages.connections.container import install_connection_providers

            app._ensure_container()  # noqa: SLF001 -- mirrors _auto_register_connections
            container = app._container  # noqa: SLF001
            assert container is not None  # _ensure_container guarantees this  # noqa: S101
            install_connection_providers(container, conn_types)

    return _ConnectionsRouter()


__all__ = ["connections"]
