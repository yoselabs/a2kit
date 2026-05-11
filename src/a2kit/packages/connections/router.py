"""Router factory for the connections plugin.

Pairs with :func:`a2kit.packages.connections.cli.connections_cli`:

.. code-block:: python

    app = a2kit.App("tracker")
    app.add_router(connections(TrackerConn))      # dispatch hook + wire scope
    app.add_cli(connections_cli(TrackerConn))     # CLI subcommands

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

    The plumbing routes through
    :func:`a2kit.packages.connections.dispatch.install_connection_dispatch`,
    which installs an async pre-step on ``app._dispatch_hook`` that awaits
    ``store.load(connection)`` and substitutes the typed ``ConnectionConfig``
    into wire kwargs before the (sync) container resolves the rest. The
    container itself contains no reference to ``"connection"``.
    """

    class _ConnectionsRouter(Router):
        name = "connections"

        def install(self, app: App) -> Any:
            from a2kit.packages.connections.dispatch import install_connection_dispatch

            install_connection_dispatch(app, conn_types)

    return _ConnectionsRouter()


__all__ = ["connections"]
