"""End-to-end DI dispatch — typed kwargs resolved per-call via App.provide()."""

from __future__ import annotations

from click.testing import CliRunner

import a2kit
from a2kit.packages.cli.builder import build_full_cli


class _Cfg:
    def __init__(self, connection: str) -> None:
        self.connection = connection


class _Store:
    def __init__(self, cfg: _Cfg) -> None:
        self.cfg = cfg

    def hello(self) -> str:
        return f"hello-from-{self.cfg.connection}"


class _Probe(a2kit.Router):
    name = "probe"

    @a2kit.read("ping")
    async def ping(self, *, store: _Store) -> dict[str, str]:
        return {"hi": store.hello()}


def test_di_resolves_store_per_call() -> None:
    app = a2kit.App("app").add_router(_Probe()).provide(_Cfg).provide(_Store)
    cli = build_full_cli(app)
    result = CliRunner().invoke(cli, ["probe", "ping", "--connection", "alpha", "--format", "json"])
    assert result.exit_code == 0, result.output
    assert "hello-from-alpha" in result.output


def test_di_strips_injectable_from_schema() -> None:
    """The agent-facing wire schema must not include ``store``."""
    app = a2kit.App("app").add_router(_Probe()).provide(_Cfg).provide(_Store)
    from a2kit.packages.cli.schemas import compute_schema

    fn = next(iter(_Probe().tools()))
    schema = compute_schema(fn, container=app.container())
    props = schema["inputSchema"].get("properties", {})
    assert "store" not in props
    assert "connection" in props


def test_di_omits_connection_when_no_chain_reaches_it() -> None:
    class _Plain(a2kit.Router):
        name = "plain"

        @a2kit.read("noop")
        async def noop(self, *, n: int) -> dict[str, int]:
            return {"n": n}

    app = a2kit.App("app").add_router(_Plain())  # no providers at all
    from a2kit.packages.cli.schemas import compute_schema

    fn = next(iter(_Plain().tools()))
    schema = compute_schema(fn, container=app.container())
    props = schema["inputSchema"].get("properties", {})
    assert "connection" not in props
    assert "n" in props


def test_di_replace_provider_overrides_factory() -> None:
    app = a2kit.App("app").add_router(_Probe()).provide(_Cfg).provide(_Store)

    def override_factory(cfg: _Cfg) -> _Store:
        return _Store(_Cfg(f"override-{cfg.connection}"))

    app.provide(_Store, override_factory)
    cli = build_full_cli(app)
    result = CliRunner().invoke(cli, ["probe", "ping", "--connection", "beta", "--format", "json"])
    assert result.exit_code == 0, result.output
    assert "override-beta" in result.output
