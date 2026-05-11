"""Mirror tests for ``a2kit.packages.connections.router``."""

from __future__ import annotations

import warnings

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
    app = a2kit.App("t")
    app.add_router(connections(_DummyConn))
    assert app.has_provider(_DummyConn)


def test_add_cli_with_marker_emits_deprecation() -> None:
    app = a2kit.App("t")
    cli = connections_cli(_DummyConn)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        app.add_cli(cli)
    deprecations = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    assert len(deprecations) == 1
    assert "add_router(connections" in str(deprecations[0].message)


def test_canonical_two_call_form_has_no_deprecation() -> None:
    app = a2kit.App("t")
    app.add_router(connections(_DummyConn))
    cli = connections_cli(_DummyConn)
    # Strip the marker to simulate explicit two-call usage.
    cli._a2kit_connections_types = None
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        app.add_cli(cli)
    deprecations = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    assert deprecations == []
    assert app.has_provider(_DummyConn)
