"""The `surfaces=` projection axis (ADR 0028 Wave 2 — surfaces-projection-axis)."""

from __future__ import annotations

import pytest

import a2kit
from a2kit._surfaces import advertised_on, matrix_for, mounted_on
from a2kit.testing import app_of


def _matrix(fn) -> dict:
    from a2kit.metadata import _get_meta

    meta = _get_meta(fn)
    assert meta is not None
    return matrix_for(meta.extras)


def test_omitted_surfaces_is_listed_everywhere() -> None:
    @a2kit.read()
    def fetch(self) -> dict:  # noqa: ANN001
        return {}

    m = _matrix(fetch)
    assert m == {"mcp": "listed", "api": "listed", "cli": "listed"}


def test_tuple_lists_named_absent_elsewhere() -> None:
    @a2kit.read(surfaces=("mcp", "cli"))
    def fetch(self) -> dict:  # noqa: ANN001
        return {}

    m = _matrix(fetch)
    assert mounted_on(m, "mcp") and advertised_on(m, "mcp")
    assert mounted_on(m, "cli") and advertised_on(m, "cli")
    assert not mounted_on(m, "api")  # absent


def test_cli_only_via_tuple() -> None:
    @a2kit.write(surfaces=("cli",))
    def op(self) -> dict:  # noqa: ANN001
        return {}

    m = _matrix(op)
    assert not mounted_on(m, "mcp")
    assert not mounted_on(m, "api")
    assert advertised_on(m, "cli")


def test_dict_escape_unlisted() -> None:
    @a2kit.read(surfaces={"cli": "unlisted"})
    def op(self) -> dict:  # noqa: ANN001
        return {}

    m = _matrix(op)
    assert mounted_on(m, "cli")
    assert not advertised_on(m, "cli")  # unlisted
    assert not mounted_on(m, "mcp")


def test_surfaces_with_legacy_kwargs_raises() -> None:
    with pytest.raises(TypeError, match="surfaces="):

        @a2kit.read(surfaces=("mcp",), expose=("api",))
        def bad(self) -> dict:  # noqa: ANN001
            return {}


def test_empty_surfaces_tuple_raises() -> None:
    with pytest.raises(ValueError, match="empty"):

        @a2kit.read(surfaces=())
        def bad(self) -> dict:  # noqa: ANN001
            return {}


@pytest.mark.asyncio
async def test_cli_only_verb_absent_from_mcp_and_http() -> None:
    """A surfaces=("cli",) verb is mounted only on the CLI, never on MCP/HTTP."""
    from click.testing import CliRunner

    from a2kit.packages.http import build_http_app
    from a2kit.packages.mcp.server import build_mcp_server
    from a2kit.runtime import build

    class Ops(a2kit.Router):
        slug = "ops"

        @a2kit.read()
        async def public_op(self, *, x: int = 0) -> dict:
            return {"x": x}

        @a2kit.write(surfaces=("cli",))
        async def trust_vault(self, *, path: str = "") -> dict:
            return {"path": path}

    app = app_of("vis", Ops())

    # MCP: trust_vault absent, public_op present.
    server = build_mcp_server(app, code_mode=False)
    mcp_names = {t.name for t in await server.list_tools()}
    assert "ops_public_op" in mcp_names
    assert "ops_trust_vault" not in mcp_names

    # HTTP: trust_vault not mounted.
    runtime = build(app)
    async with runtime:
        api = build_http_app(runtime)
        mounted = {getattr(r, "path", None) for r in api.routes}
        assert "/ops_public_op" in mounted
        assert "/ops_trust_vault" not in mounted

    # CLI: trust_vault present (operator surface).
    cli = app.cli.bind(build(app))
    out = CliRunner().invoke(cli, ["ops", "--help"]).output
    assert "trust_vault" in out
