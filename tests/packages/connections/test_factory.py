"""get_conn_factory wires app store + Depends-style factory for tool DI."""

from __future__ import annotations

import asyncio
import inspect

import pytest

from a2kit.app import App
from a2kit.packages.connections import ConnectionNotFound, ConnectionStore, get_conn_factory
from .conftest import WidgetConfig


def test_factory_returns_loaded_connection(
    widget_store: ConnectionStore[WidgetConfig],
) -> None:
    asyncio.run(widget_store.save(WidgetConfig(key=("prod",), token="literal")))
    app = App("test")
    app.connect(WidgetConfig)
    app._stores[WidgetConfig] = widget_store  # inject our tmp_path-backed store
    get_conn = get_conn_factory(app, WidgetConfig)
    info = asyncio.run(get_conn(connection="prod"))
    assert info.token == "literal"


def test_factory_signature_has_kwonly_connection() -> None:
    app = App("test")
    app.connect(WidgetConfig)
    get_conn = get_conn_factory(app, WidgetConfig)
    sig = inspect.signature(get_conn)
    assert "connection" in sig.parameters
    assert sig.parameters["connection"].kind is inspect.Parameter.KEYWORD_ONLY


def test_factory_raises_connection_not_found(
    widget_store: ConnectionStore[WidgetConfig],
) -> None:
    app = App("test")
    app.connect(WidgetConfig)
    app._stores[WidgetConfig] = widget_store
    get_conn = get_conn_factory(app, WidgetConfig)
    with pytest.raises(ConnectionNotFound):
        asyncio.run(get_conn(connection="ghost"))
