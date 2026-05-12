"""a2kit.packages.connections — pydantic-settings-backed Connection store + CLI."""

from __future__ import annotations

from typing import TYPE_CHECKING

from a2kit.packages.connections.cli import connections_cli
from a2kit.packages.connections.config import ConnectionConfig, default_config_dir
from a2kit.packages.connections.dispatch import install_connection_dispatch
from a2kit.packages.connections.exceptions import (
    ConnectionNotFound,
    EnvVarNotFound,
    InvalidConnectionKey,
    KeyArityMismatch,
    KeyFieldMissing,
    OpResolutionError,
    TokenResolutionError,
    WriteNotAllowed,
)
from a2kit.packages.connections.filters import EphemeralAwareStore, FilteredStore, scope_filter
from a2kit.packages.connections.store import ConnectionStore

if TYPE_CHECKING:
    from a2kit.app import App


def install_connections(app: App, *conn_types: type[ConnectionConfig]) -> App:
    """Install the connections dispatch hook + typed wire scope on ``app``.

    Pairs with :func:`connections_cli`:

    .. code-block:: python

        app = a2kit.App("tracker")
        install_connections(app, TrackerConn)        # dispatch hook + wire scope
        app.add_cli(connections_cli(TrackerConn))    # CLI subcommands

    Imperative replacement for the previous ``connections(*types)`` Router
    factory. The Router carried no tools — only an attach hook — so it
    failed the explicit-router-surface invariant (``slug`` / ``tools`` /
    ``providers`` / ``lifespan`` only). This function performs the same
    wiring with one call instead of a fake Router.

    Returns ``app`` to allow fluent chaining.
    """
    install_connection_dispatch(app, conn_types)
    return app


__all__ = [
    "ConnectionConfig",
    "ConnectionNotFound",
    "ConnectionStore",
    "EnvVarNotFound",
    "EphemeralAwareStore",
    "FilteredStore",
    "InvalidConnectionKey",
    "KeyArityMismatch",
    "KeyFieldMissing",
    "OpResolutionError",
    "TokenResolutionError",
    "WriteNotAllowed",
    "connections_cli",
    "default_config_dir",
    "install_connections",
    "scope_filter",
]
