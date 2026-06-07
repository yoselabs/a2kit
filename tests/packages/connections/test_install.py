"""Tests for ``install_connections`` and discovery-surface invariants.

v0.30 (explicit-router-surface): the previous ``connections(*types)`` Router
factory was deleted because the Router-as-marker pattern leaks a hidden
fifth attribute (``_a2kit_attach``) on top of the closed
slug/tools/providers/lifespan surface. The replacement is an imperative
:func:`install_connections` call.

Post-Q2 single-call wiring: ``install_connections`` registers dispatch hook
+ wire scope AND adds the ``connections`` CLI subcommand group. No
separate ``add_cli(connections_cli(...))`` call required.
"""

from __future__ import annotations

import a2kit
from a2kit.packages.connections import (
    ConnectionConfig,
    install_connections,
)


class _DummyConn(ConnectionConfig):
    """Minimal ConnectionConfig subclass for tests."""

    key_fields: tuple[str, ...] = ()


def test_install_connections_registers_provider() -> None:
    """install_connections registers a stub provider so container.has() is True
    and the dispatch hook substitutes typed configs into wire kwargs."""
    app = a2kit.App("t")
    install_connections(app, _DummyConn)
    assert app.has_provider(_DummyConn)


def test_install_connections_registers_connection_wire_scope() -> None:
    """install_connections teaches the container about the ``connection`` scope."""
    app = a2kit.App("t")
    install_connections(app, _DummyConn)
    scopes = app.container().wire_scopes()
    assert "connection" in scopes
    assert _DummyConn in scopes["connection"]


def test_install_connections_registers_cli_group() -> None:
    """install_connections also adds the `connections` Click subcommand group."""
    app = a2kit.App("t")
    install_connections(app, _DummyConn)
    cli_extras = app.cli_extras()
    assert any(getattr(c, "name", None) == "connections" for c in cli_extras)


def test_add_cli_does_not_auto_install_provider() -> None:
    """add_cli alone (without install_connections) does not register providers.
    Regression guard: there is no Router-as-marker pattern.
    """
    from a2kit.packages.connections.cli import connections_cli

    app = a2kit.App("t")
    cli = connections_cli(_DummyConn)
    app.add_cli(cli)
    assert not app.has_provider(_DummyConn)


def test_add_router_ignores_underscore_marker() -> None:
    """The discovery surface is closed to slug/tools/providers/lifespan.
    Any underscore-prefixed class attribute on a Router subclass must NOT
    be read by App.add_router. Regression guard against re-introducing
    ``_a2kit_attach`` or any sibling marker.
    """
    sentinel = {"called": False}

    def _hidden_hook(_app: a2kit.App) -> None:
        sentinel["called"] = True

    class _Sneaky(a2kit.Router):
        slug = "sneaky"
        _a2kit_attach = staticmethod(_hidden_hook)

    app = a2kit.App("t").add_router(_Sneaky())
    assert sentinel["called"] is False, "App.add_router must not invoke _a2kit_attach or any underscored marker"
