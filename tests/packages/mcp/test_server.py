"""``build_mcp_server`` registration round-trip tests."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

import a2kit
from a2kit.packages.mcp import build_mcp_server
from a2kit.testing import app_of


class _SampleRouter(a2kit.Router):
    slug = "sample"
    name = "sample"

    @a2kit.read()
    async def ping(self, *, name: str = "world") -> dict[str, str]:
        return {"hello": name}

    @a2kit.list_("id", "name", page_size=2)
    async def rows(self) -> list[dict[str, Any]]:
        return [
            {"id": 1, "name": "a", "extra": "drop"},
            {"id": 2, "name": "b", "extra": "drop"},
            {"id": 3, "name": "c", "extra": "drop"},
        ]


@pytest.fixture
def app() -> a2kit.App:
    return app_of("sample-app", _SampleRouter())


def test_build_mcp_server_returns_fastmcp(app: a2kit.App) -> None:
    from fastmcp import FastMCP

    server = build_mcp_server(app, code_mode=False)
    assert isinstance(server, FastMCP)
    assert server.name == "sample-app"


def test_tools_registered_with_a2kit_meta(app: a2kit.App) -> None:
    server = build_mcp_server(app, code_mode=False)

    async def _check() -> None:
        tools = {t.name: t for t in await server.list_tools()}
        assert "sample_ping" in tools
        ping = tools["sample_ping"]
        meta = ping.meta or {}
        a2kit_meta = meta.get("a2kit")
        assert isinstance(a2kit_meta, dict)
        assert a2kit_meta["verb"] == "read"
        assert a2kit_meta["tool_name"] == "ping"
        assert "read" in a2kit_meta["tags"]
        assert a2kit_meta["extras"]["router_slug"] == "sample"
        # report_type is dropped from wire (non-JSON-serializable)
        assert "report_type" not in a2kit_meta["extras"]
        # annotations serialized via model_dump
        ann = a2kit_meta["annotations"]
        assert isinstance(ann, dict)

    asyncio.run(_check())


def test_list_view_settings_round_trip(app: a2kit.App) -> None:
    server = build_mcp_server(app, code_mode=False)

    async def _check() -> None:
        tools = {t.name: t for t in await server.list_tools()}
        rows = tools["sample_rows"]
        a2kit_meta = (rows.meta or {})["a2kit"]
        lv = a2kit_meta["extras"]["list_view"]
        assert list(lv["default_fields"]) == ["id", "name"]
        assert lv["page_size"] == 2

    asyncio.run(_check())


def test_forwards_fastmcp_kwargs(app: a2kit.App) -> None:
    """`auth=None` is the easy passthrough; the real test is that an arbitrary
    kwarg lands on `FastMCP.__init__` without a2kit translation."""
    server = build_mcp_server(app, instructions="test instructions", mask_error_details=True)
    assert server.instructions == "test instructions"


def test_unknown_fastmcp_kwarg_propagates(app: a2kit.App) -> None:
    with pytest.raises(TypeError):
        build_mcp_server(app, definitely_not_a_fastmcp_param=True)


def test_enricher_fires_before_registration() -> None:
    """An instance-decorator enricher wraps fn before FunctionTool.from_function;
    the framework translates raised exceptions to the registered AppError type."""
    from a2effect import AppError

    fired: list[Exception] = []

    class EnrichedError(AppError):
        kind = "infra"

    class R(a2kit.Router):
        slug = "r"
        name = "r"

        @a2kit.read()
        async def boom(self) -> dict[str, str]:
            raise RuntimeError("kaboom")

    router = R()

    @router.enricher
    def my_enricher(exc: RuntimeError) -> EnrichedError | None:
        fired.append(exc)
        return EnrichedError(f"enriched: {exc!s}")

    app = app_of("e", router)
    server = build_mcp_server(app, code_mode=False)

    async def _check() -> None:
        # NOTE: full wire-envelope rendering lands in Group 14 (MCP surface
        # rendering). For now we verify the EnricherStage translates the
        # raised RuntimeError into the registered AppError type.
        from fastmcp.exceptions import ToolError

        tools = {t.name: t for t in await server.list_tools()}
        bt = tools["r_boom"]
        with pytest.raises((ToolError, EnrichedError)):
            await bt.fn()  # ty: ignore[unresolved-attribute]  # why: stub object exposes attributes only at runtime; static checker can't see them

    asyncio.run(_check())
    assert len(fired) == 1


def test_sync_and_async_tools_both_register() -> None:
    class R(a2kit.Router):
        slug = "r"
        name = "r"

        @a2kit.read()
        def sync_one(self) -> dict[str, int]:
            return {"x": 1}

        @a2kit.read()
        async def async_one(self) -> dict[str, int]:
            return {"x": 2}

    app = app_of("a", R())
    server = build_mcp_server(app, code_mode=False)

    async def _check() -> None:
        tools = {t.name: t for t in await server.list_tools()}
        assert {"r_sync_one", "r_async_one"}.issubset(tools.keys())

    asyncio.run(_check())


# --- MCP Apps: `authorize=` enforcement on `@app.mcp.*` (Track 2) ----------- #
#
# The `@app.mcp.*` escape hatch bypasses the dispatch pipeline (so it never
# rides `AuthorizeGateStage`). The captured `authorize=` MUST still be enforced
# at registration time, honoring the `tool-authorization` "uniform across
# surfaces" requirement — the hatch is not an authorization gap.

from fastmcp import Client  # noqa: E402

from a2kit.packages.context import Principal, request_scope  # noqa: E402


def _admin_only(*, principal: Principal) -> bool:
    return "admin" in principal.scopes


def _app_with_gated_mcp_tool() -> tuple[a2kit.App, list[int]]:
    body_calls: list[int] = []
    app = app_of("mcp-authz")

    @app.mcp.tool(name="admin_dash", authorize=_admin_only)
    async def admin_dash(*, region: str = "eu") -> dict[str, str]:
        body_calls.append(1)
        return {"region": region}

    return app, body_calls


async def _call_mcp_with_principal(app: a2kit.App, name: str, principal: Principal) -> Any:
    server = build_mcp_server(app, code_mode=False)
    token = request_scope.publish(principal)
    try:
        async with Client(transport=server) as c:
            return await c.call_tool(name, {}, raise_on_error=False)
    finally:
        request_scope.reset(token)


def test_mcp_tool_authorize_denies_non_admin() -> None:
    app, body_calls = _app_with_gated_mcp_tool()
    result = asyncio.run(_call_mcp_with_principal(app, "admin_dash", Principal(subject="u1", scopes=frozenset())))
    assert result.is_error is True
    assert result.structured_content is not None
    assert result.structured_content["error"]["type"] == "AuthorizationDenied"
    assert body_calls == []


def test_mcp_tool_authorize_allows_admin() -> None:
    app, body_calls = _app_with_gated_mcp_tool()
    result = asyncio.run(_call_mcp_with_principal(app, "admin_dash", Principal(subject="u1", scopes=frozenset({"admin"}))))
    assert result.is_error is False
    assert body_calls == [1]


# --- MCP Apps: ui:// resource wire shape (Track 1) -------------------------- #

_UI_HTML = "<!doctype html><h1>dash</h1>"


def _build_ui_app_server() -> Any:
    # a2kit forwards the `app=` payload verbatim, so the camelCase dict form
    # (no `fastmcp.apps` import) and an `AppConfig` produce identical wire
    # output. The dict form is what we assert — it is a2kit's actual contract.
    app = app_of("mcp-apps-wire")

    @app.mcp.tool(name="show_dash", app={"resourceUri": "ui://mcp-apps-wire/view.html"})
    async def show_dash(*, region: str = "eu") -> dict[str, str]:
        return {"region": region}

    @app.mcp.resource(
        uri="ui://mcp-apps-wire/view.html",
        app={"csp": {"connectDomains": ["https://api.example.com"]}},
    )
    async def view() -> str:
        return _UI_HTML

    return build_mcp_server(app, code_mode=False)


async def _list_ui(server: Any) -> tuple[dict[str, Any], dict[str, Any], Any]:
    async with Client(transport=server) as c:
        tools = {t.name: t for t in await c.list_tools()}
        resources = {str(r.uri): r for r in await c.list_resources()}
        read = await c.read_resource("ui://mcp-apps-wire/view.html")
    return tools, resources, read


def test_mcp_app_tool_declares_ui_resource_uri() -> None:
    tools, _, _ = asyncio.run(_list_ui(_build_ui_app_server()))
    assert tools["show_dash"].meta["ui"]["resourceUri"] == "ui://mcp-apps-wire/view.html"


def test_mcp_app_resource_served_with_mcp_app_mime_and_csp() -> None:
    _, resources, read = asyncio.run(_list_ui(_build_ui_app_server()))
    r = resources["ui://mcp-apps-wire/view.html"]
    assert r.mimeType == "text/html;profile=mcp-app"
    assert r.meta["ui"]["csp"]["connectDomains"] == ["https://api.example.com"]
    # a2kit constructs no UI bytes — the author's HTML passes through unchanged.
    assert read[0].text == _UI_HTML


def test_building_mcp_app_imports_no_ui_framework() -> None:
    import sys

    _build_ui_app_server()
    assert "prefab" not in sys.modules


def test_prefab_trigger_forwards_without_coupling() -> None:
    import sys

    app = app_of("mcp-apps-prefab-fwd")

    @app.mcp.tool(name="p", app=True)
    async def p(*, x: int = 1) -> dict[str, int]:
        return {"x": x}

    server = build_mcp_server(app, code_mode=False)

    async def _meta() -> dict[str, Any]:
        async with Client(transport=server) as c:
            return {t.name: t for t in await c.list_tools()}

    tools = asyncio.run(_meta())
    assert tools["p"].meta["ui"] is True
    assert "prefab" not in sys.modules


def test_init_does_not_export_more_than_build_mcp_server() -> None:
    import a2kit.packages.mcp as pkg

    assert pkg.__all__ == ["build_mcp_server"]
