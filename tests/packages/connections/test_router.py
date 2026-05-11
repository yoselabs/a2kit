"""Mirror tests for ``a2kit.packages.connections.router``."""

from __future__ import annotations

import a2kit
from a2kit.packages.connections import connections, connections_cli
from a2kit.packages.connections.config import ConnectionConfig


class _DummyConn(ConnectionConfig):
    """Minimal ConnectionConfig subclass for tests."""

    key_fields: tuple[str, ...] = ()


def test_connections_returns_router() -> None:
    router = connections(_DummyConn)
    assert router.slug == "connections"


def test_add_router_installs_provider() -> None:
    """v0.27: connections Router installs a stub provider so container.has() is True
    and the dispatch hook substitutes typed configs into wire kwargs."""
    app = a2kit.App("t")
    app.add_router(connections(_DummyConn))
    assert app.has_provider(_DummyConn)


def test_add_router_registers_connection_wire_scope() -> None:
    """v0.27: connections Router teaches the container about the ``connection`` scope."""
    app = a2kit.App("t")
    app.add_router(connections(_DummyConn))
    scopes = app.container().wire_scopes()
    assert "connection" in scopes
    assert _DummyConn in scopes["connection"]


def test_add_cli_does_not_auto_install_provider() -> None:
    """v0.27: add_cli no longer auto-registers providers via hidden marker.
    Consumers explicitly call add_router(connections(X)) + add_cli(connections_cli(X)).
    """
    app = a2kit.App("t")
    cli = connections_cli(_DummyConn)
    app.add_cli(cli)
    assert not app.has_provider(_DummyConn)


def test_canonical_two_call_form() -> None:
    app = a2kit.App("t")
    app.add_router(connections(_DummyConn))
    app.add_cli(connections_cli(_DummyConn))
    assert app.has_provider(_DummyConn)
