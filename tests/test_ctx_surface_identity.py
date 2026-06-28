"""ctx-surface-identity (ADR 0028 Wave 3) — each Surface stamps its identity.

A tool dispatched over MCP, posted to ``/api``, or run from the CLI runs the
*same* body. This change extends ADR-0027's ``_CallScope`` with two optional
fields — ``surface`` (``"mcp"`` | ``"api"`` | ``"cli"``) and an OPTIONAL
``surface_client_id`` — so a tool body and the durable call-record can both
read which surface drove the call.

Additive: new fields / kwargs default ``None``; existing callers are
untouched. The surface name comes from the dispatching surface (baked into the
per-surface ``ToolBuildSpec``), NOT from sniffing the ctx type.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, cast

import a2kit
import a2kit.log
from a2kit.packages.context import StderrToolContext
from a2kit.packages.log import bind_call_scope
from a2kit.packages.log.scope import _CallScope, _active_scope
from a2kit.testing import app_of

from tests._typed_records import A2kitLogRecord

if TYPE_CHECKING:
    from a2kit.runtime import AppRuntime

# --------------------------------------------------------------------------- #
# Probe helpers — a verb whose body records the active surface identity.
# --------------------------------------------------------------------------- #


def _probe_app(captured: dict[str, Any]) -> a2kit.App:
    """An App with one verb ``probe_whoami`` recording the active surface."""

    class Probe(a2kit.Router):
        slug = "probe"

        @a2kit.read()
        async def whoami(self) -> dict[str, str]:
            captured["surface"] = a2kit.log.current_surface()
            captured["client_id"] = a2kit.log.current_surface_client_id()
            return {"ok": "yes"}

    return app_of("probe-app", Probe())


async def _dispatch_mcp(app: a2kit.App) -> None:
    from fastmcp import Client

    from a2kit.packages.mcp.server import build_mcp_server

    server = build_mcp_server(app)
    async with Client(transport=server) as c:
        await c.call_tool("probe_whoami", {}, raise_on_error=False)


def _dispatch_http(app: a2kit.App) -> None:
    from fastapi.testclient import TestClient

    from a2kit.packages.http import build_http_app
    from a2kit.runtime import build

    async def _run() -> None:
        runtime = build(app)
        async with runtime:
            api = build_http_app(runtime)
            with TestClient(api) as client:
                client.post("/probe_whoami", json={})

    asyncio.run(_run())


def _dispatch_cli(app: a2kit.App) -> None:
    from click.testing import CliRunner

    from a2kit.packages.cli.builder import build_full_cli

    cli = build_full_cli(app)
    CliRunner().invoke(cli, ["probe", "whoami"])


# --------------------------------------------------------------------------- #
# §0 — Confirm the gap (baseline integration; RED today).
# --------------------------------------------------------------------------- #


def test_surface_identity_absent_today() -> None:
    """The same verb, dispatched on each surface, can report its surface."""
    seen: set[str | None] = set()
    for dispatch in (_dispatch_mcp, _dispatch_http, _dispatch_cli):
        captured: dict[str, Any] = {}
        app = _probe_app(captured)
        if dispatch is _dispatch_mcp:
            asyncio.run(_dispatch_mcp(app))
        else:
            dispatch(app)
        seen.add(captured.get("surface"))
    assert seen == {"mcp", "api", "cli"}


# --------------------------------------------------------------------------- #
# §1 — Extend the per-call scope.
# --------------------------------------------------------------------------- #


def test_call_scope_has_surface_fields() -> None:
    scope = _CallScope()
    assert scope.surface is None
    assert scope.surface_client_id is None


def test_bind_call_scope_stamps_surface() -> None:
    ctx = StderrToolContext()
    with bind_call_scope(ctx=ctx, surface="mcp", surface_client_id="c1") as scope:
        assert scope.surface == "mcp"
        assert scope.surface_client_id == "c1"
        active = _active_scope()
        assert active is not None
        assert active.surface == "mcp"
        assert active.surface_client_id == "c1"
    # Backward-compat: omitting them yields None for both.
    with bind_call_scope(ctx=ctx) as scope2:
        assert scope2.surface is None
        assert scope2.surface_client_id is None


# --------------------------------------------------------------------------- #
# §2 — Read accessor.
# --------------------------------------------------------------------------- #


def test_current_surface_accessor() -> None:
    # Outside any dispatch: None, never raises.
    assert a2kit.log.current_surface() is None
    assert a2kit.log.current_surface_client_id() is None
    ctx = StderrToolContext()
    with bind_call_scope(ctx=ctx, surface="api", surface_client_id="abc"):
        assert a2kit.log.current_surface() == "api"
        assert a2kit.log.current_surface_client_id() == "abc"
    # Restored to None after the scope closes.
    assert a2kit.log.current_surface() is None


# --------------------------------------------------------------------------- #
# §3 — Stamp at the dispatch boundary (real transports).
# --------------------------------------------------------------------------- #


def test_mcp_dispatch_stamps_surface() -> None:
    captured: dict[str, Any] = {}
    app = _probe_app(captured)
    asyncio.run(_dispatch_mcp(app))
    assert captured["surface"] == "mcp"


def test_http_dispatch_stamps_surface() -> None:
    captured: dict[str, Any] = {}
    app = _probe_app(captured)
    _dispatch_http(app)
    assert captured["surface"] == "api"


def test_cli_dispatch_stamps_surface() -> None:
    captured: dict[str, Any] = {}
    app = _probe_app(captured)
    _dispatch_cli(app)
    assert captured["surface"] == "cli"


def test_surface_client_id_optional() -> None:
    """The CLI ctx has no client_id → surface_client_id is None, no crash."""
    captured: dict[str, Any] = {}
    app = _probe_app(captured)
    _dispatch_cli(app)
    assert captured["surface"] == "cli"
    assert captured["client_id"] is None


def test_surface_client_id_from_ctx() -> None:
    """When the bound ctx exposes ``client_id``, it lands on the scope.

    Stage-level: the in-memory MCP transport assigns no real ``client_id``,
    so the present-id half of §3.4 is pinned by driving ``CallScopeStage``
    with a ctx that carries one (mirrors a live FastMCP ``Context``).
    """
    from a2kit.packages.dispatch.spec import SYNTHESIZED_CTX_PARAM_NAME, ToolBuildSpec
    from a2kit.packages.dispatch.stages import CallScopeStage

    class _Ctx:
        client_id = "mcp-client-7"

    captured: dict[str, Any] = {}

    async def fn() -> None:
        captured["surface"] = a2kit.log.current_surface()
        captured["client_id"] = a2kit.log.current_surface_client_id()

    spec = ToolBuildSpec(app=cast("AppRuntime", None), router=None, meta=None, surface="mcp")
    wrapped = CallScopeStage().wrap(fn, spec)
    asyncio.run(wrapped(**{SYNTHESIZED_CTX_PARAM_NAME: _Ctx()}))
    assert captured["surface"] == "mcp"
    assert captured["client_id"] == "mcp-client-7"


# --------------------------------------------------------------------------- #
# §4 — Surface rides the records.
# --------------------------------------------------------------------------- #


def test_log_record_carries_surface() -> None:
    import logging

    from a2kit.packages.log.scope import _CallScopeFilter

    record = logging.LogRecord("a2kit", logging.INFO, __file__, 1, "m", None, None)
    filt = _CallScopeFilter()
    # Outside a dispatch: surface is None.
    filt.filter(record)
    assert cast("A2kitLogRecord", record).surface is None
    # Inside a dispatch: surface is the active scope's surface.
    ctx = StderrToolContext()
    with bind_call_scope(ctx=ctx, surface="mcp"):
        record2 = logging.LogRecord("a2kit", logging.INFO, __file__, 1, "m", None, None)
        filt.filter(record2)
        assert cast("A2kitLogRecord", record2).surface == "mcp"


def test_call_record_carries_surface() -> None:
    from a2kit.packages.log import CallRecord

    record = CallRecord(call_id="x", surface="api")
    assert record.surface == "api"
    assert "surface" in record.to_row()
    assert record.to_row()["surface"] == "api"


# --------------------------------------------------------------------------- #
# §5 — Isolation & absence.
# --------------------------------------------------------------------------- #


async def test_concurrent_surfaces_isolated() -> None:
    ctx = StderrToolContext()

    async def _leg(surface: str) -> str | None:
        with bind_call_scope(ctx=ctx, surface=surface):
            await asyncio.sleep(0)
            return a2kit.log.current_surface()

    results = await asyncio.gather(_leg("mcp"), _leg("api"), _leg("cli"))
    assert set(results) == {"mcp", "api", "cli"}


def test_nested_dispatch_surface_shadows_and_restores() -> None:
    ctx = StderrToolContext()
    with bind_call_scope(ctx=ctx, surface="api"):
        assert a2kit.log.current_surface() == "api"
        with bind_call_scope(ctx=ctx, surface="mcp"):
            assert a2kit.log.current_surface() == "mcp"
        # Outer restores after the inner dispatch returns.
        assert a2kit.log.current_surface() == "api"


def test_unresolvable_surface_is_none() -> None:
    ctx = StderrToolContext()
    with bind_call_scope(ctx=ctx):
        assert a2kit.log.current_surface() is None
