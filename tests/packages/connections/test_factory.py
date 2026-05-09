"""get_conn_factory wires the Connections plugin's store + Depends factory."""

from __future__ import annotations

import asyncio
import inspect

import pytest

from a2kit.app import App
from a2kit.packages.connections import (
    ConnectionNotFound,
    ConnectionStore,
    Connections,
    get_conn_factory,
)

from .conftest import WidgetConfig


def _app_with_store(widget_store: ConnectionStore[WidgetConfig]) -> App:
    """Build an App with Connections plugin and an injected pre-built store."""
    plugin = Connections()
    app = App("test").use(plugin).use(WidgetConfig)
    plugin._stores[WidgetConfig] = widget_store  # inject tmp_path-backed store
    return app


def test_factory_returns_loaded_connection(
    widget_store: ConnectionStore[WidgetConfig],
) -> None:
    asyncio.run(widget_store.save(WidgetConfig(key=("prod",), token="literal")))
    app = _app_with_store(widget_store)
    get_conn = get_conn_factory(app, WidgetConfig)
    info = asyncio.run(get_conn(connection="prod"))
    assert info.token == "literal"


def test_factory_signature_has_kwonly_connection() -> None:
    app = App("test").use(Connections()).use(WidgetConfig)
    get_conn = get_conn_factory(app, WidgetConfig)
    sig = inspect.signature(get_conn)
    assert "connection" in sig.parameters
    assert sig.parameters["connection"].kind is inspect.Parameter.KEYWORD_ONLY


def test_factory_raises_connection_not_found(
    widget_store: ConnectionStore[WidgetConfig],
) -> None:
    app = _app_with_store(widget_store)
    get_conn = get_conn_factory(app, WidgetConfig)
    with pytest.raises(ConnectionNotFound):
        asyncio.run(get_conn(connection="ghost"))


def test_factory_raises_when_no_connections_plugin() -> None:
    """Without `app.use(Connections())`, factory creation should error out clearly."""
    app = App("test")
    with pytest.raises(RuntimeError, match="no Connections plugin"):
        get_conn_factory(app, WidgetConfig)
