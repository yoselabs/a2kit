"""The connections plugin installer — single-call composition-time wiring."""

from __future__ import annotations

from typing import TYPE_CHECKING

from a2kit.packages.connections.cli import connections_cli as _connections_cli
from a2kit.packages.connections.dispatch import install_connection_dispatch

if TYPE_CHECKING:
    from a2kit.app import App
    from a2kit.packages.connections.config import ConnectionConfig


def install_connections(app: App, *conn_types: type[ConnectionConfig]) -> App:
    """Install the connections plugin on ``app`` — single entry point.

    Wires three things in one call:

    1. The connection-string dispatch hook (resolves ``connection: str``
       wire input into typed ``ConnectionConfig`` instances).
    2. The ``"connection"`` wire scope on the App's DI container.
    3. The ``connections`` Click subcommand group on the CLI
       (``login`` / ``logout`` / ``list`` / ``show`` / ``delete``).

    Composition-time wiring — call it on the ``App`` before handing it to
    a finisher. Usage::

        app = a2kit.App("tracker")
        install_connections(app, TrackerConn)   # complete wiring

    No separate ``add_cli`` call needed. The plugin owns its CLI shape
    end-to-end. Returns ``app`` for fluent chaining.
    """
    install_connection_dispatch(app, conn_types)
    app.add_cli(_connections_cli(*conn_types))
    return app
