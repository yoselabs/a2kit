"""End-to-end DI dispatch — v0.27: connection-string resolution via dispatch hook.

The container itself knows nothing about ``"connection"``. The connections
package installs a dispatch hook that pulls ``connection: str`` out of wire
kwargs, awaits the store load, and substitutes the typed config before the
container resolves the rest synchronously.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from click.testing import CliRunner

import a2kit
from a2kit.packages.cli.builder import build_full_cli
from a2kit.packages.connections import install_connections
from a2kit.packages.connections.config import ConnectionConfig


class _Cfg(ConnectionConfig):
    """Test connection config — its loaded instance carries 'name' from the
    connection string the dispatch hook awaits via the store."""

    key_fields: tuple[str, ...] = ("name",)
    name: str = ""


class _Store:
    def __init__(self, cfg: _Cfg) -> None:
        self.cfg = cfg

    def hello(self) -> str:
        return f"hello-from-{self.cfg.name}"


class _Probe(a2kit.Router):
    slug = "probe"
    name = "probe"

    @a2kit.read()
    async def ping(self, *, store: _Store) -> dict[str, str]:
        return {"hi": store.hello()}

    tools = (ping,)


async def _fake_load(self: Any, *args: Any, **kwargs: Any) -> _Cfg:
    """Fake ConnectionStore.load that constructs _Cfg from the connection
    string without touching disk. Used by tests that need predictable
    resolution without TOML files."""
    name = args[0] if args else kwargs.get("name", "default")
    return _Cfg(key=(name,), name=name)


def test_di_resolves_store_per_call() -> None:
    """Wire ``--connection alpha`` flows through the dispatch hook → typed _Cfg → _Store."""
    app = a2kit.App("app").add_router(_Probe()).provide(_Store)
    install_connections(app, _Cfg)
    cli = build_full_cli(app)
    with patch("a2kit.packages.connections.store.ConnectionStore.load", _fake_load):
        result = CliRunner().invoke(cli, ["probe", "ping", "--connection", "alpha", "--format", "json"])
    assert result.exit_code == 0, result.output
    assert "hello-from-alpha" in result.output


def test_di_strips_injectable_from_schema() -> None:
    """The agent-facing wire schema must not include injectable ``store``;
    it should synthesize a wire ``connection: str``."""
    app = a2kit.App("app").add_router(_Probe()).provide(_Store)
    install_connections(app, _Cfg)
    from a2kit.schema import compute_schema

    fn = next(iter(_Probe().bound_tools()))
    schema = compute_schema(fn, container=app.container())
    props = schema["inputSchema"].get("properties", {})
    assert "store" not in props
    assert "connection" in props


def test_di_omits_connection_when_no_chain_reaches_it() -> None:
    class _Plain(a2kit.Router):
        slug = "plain"
        name = "plain"

        @a2kit.read()
        async def noop(self, *, n: int) -> dict[str, int]:
            return {"n": n}

        tools = (noop,)

    app = a2kit.App("app").add_router(_Plain())
    from a2kit.schema import compute_schema

    fn = next(iter(_Plain().bound_tools()))
    schema = compute_schema(fn, container=app.container())
    props = schema["inputSchema"].get("properties", {})
    assert "connection" not in props
    assert "n" in props


def test_di_replace_provider_overrides_factory() -> None:
    app = a2kit.App("app").add_router(_Probe()).provide(_Store)
    install_connections(app, _Cfg)

    def override_factory(cfg: _Cfg) -> _Store:
        return _Store(_Cfg(key=(f"override-{cfg.name}",), name=f"override-{cfg.name}"))

    app.provide(_Store, override_factory)
    cli = build_full_cli(app)
    with patch("a2kit.packages.connections.store.ConnectionStore.load", _fake_load):
        result = CliRunner().invoke(cli, ["probe", "ping", "--connection", "beta", "--format", "json"])
    assert result.exit_code == 0, result.output
    assert "override-beta" in result.output
