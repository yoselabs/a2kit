"""BDD: LDD primitives work in dispatched tools that don't declare ``ctx``.

Closes a2web round-10 Friction B. The framework's wrapper synthesizes
ctx into ambient state for every dispatched tool, regardless of
whether the tool body declares ``ctx: a2kit.ToolContext``. LDD
primitives find a non-None ambient ctx and emit through both wire
and sink paths.

Aligns with LDD's log-driven-development purpose: sink emission
(structured logs persisted for post-hoc reading by AI agents) is
the primary contract; wire emission is the secondary live-UX path.
Neither should fail because the tool author chose not to take ctx
in their body's signature.
"""

from __future__ import annotations

import asyncio
import json as _json
from typing import Any

import pytest

import a2kit
from a2kit.ldd import event as ldd_event
from a2kit.testing import client


class _NoCtxRouter(a2kit.Router):
    """Router whose tool body emits LDD but does not declare ctx."""

    slug = "noctx_emit"

    @a2kit.read()
    async def fire(self) -> dict[str, str]:
        # Tool body emits LDD with no ctx in signature.
        await ldd_event("fired", marker="value-1")
        return {"ok": "yes"}

    tools = (fire,)


def test_mcp_dispatch_emits_ldd_without_ctx_param() -> None:
    """Tool on a Router with NO ctx param emits a2kit.ldd.event.
    Drive through real fastmcp.Client transport.
    Assert: invocation completes; client.events captures the event.
    """
    app = a2kit.AppBuilder("noctx-mcp").add_router(_NoCtxRouter()).build()

    async def go() -> dict[str, Any]:
        async with client(app) as c:
            result = await c.invoke("fire")
            assert result == {"ok": "yes"}
            assert any(e["name"] == "fired" for e in c.events), f"event 'fired' not captured; got: {c.events}"
            captured = next(e for e in c.events if e["name"] == "fired")
            assert captured["payload"] == {"marker": "value-1"}
            assert "elapsed_ms" in captured
            return result

    asyncio.run(go())


def test_mcp_dispatch_no_raise_for_ldd_without_ctx() -> None:
    """Regression: real-MCP dispatch of a no-ctx tool that emits LDD
    must NOT raise AmbientContextMissing (Mode B retires inside
    framework dispatch)."""
    from fastmcp.exceptions import ToolError

    app = a2kit.AppBuilder("noctx-mcp-no-raise").add_router(_NoCtxRouter()).build()

    async def go() -> None:
        async with client(app) as c:
            try:
                await c.invoke("fire")
            except ToolError as exc:  # pragma: no cover -- regression assertion
                payload = _json.loads(str(exc))
                pytest.fail(f"dispatch should not raise; got {payload['class']}: {payload['message']}")

    asyncio.run(go())


def test_cli_runtime_emits_ldd_without_ctx_param(capsys: pytest.CaptureFixture[str]) -> None:
    """Same scenario via the CLI runtime path. Stderr should contain an
    LDD-formatted event line."""
    from a2kit.metadata import get_meta
    from a2kit.packages.cli.runtime import invoke_tool_sync
    from a2kit.packages.dispatch import ToolBuildSpec

    @a2kit.read()
    async def fire_no_ctx() -> dict[str, str]:
        await ldd_event("fired-cli", marker="cli-value")
        return {"ok": "cli"}

    # A tool whose signature declares no ctx — mirrors the CLI subcommand
    # path; the LDD stage falls back to a synthesized StderrToolContext.
    spec = ToolBuildSpec(app=a2kit.AppBuilder("ldd-cli").build(), router=None, meta=get_meta(fire_no_ctx))
    out = invoke_tool_sync(fire_no_ctx, {}, fmt="json", spec=spec)
    assert "cli" in out

    captured = capsys.readouterr()
    # CLI runtime emits LDD event lines to stderr in the wire format.
    assert "fired-cli" in captured.err, f"LDD event not in stderr; got: {captured.err!r}"


def test_tool_with_ctx_still_receives_it() -> None:
    """Regression: tools that DO declare ctx continue to receive it
    as a kwarg (today's behaviour preserved)."""

    captured_ctx: list[Any] = []

    class _WithCtxRouter(a2kit.Router):
        slug = "withctx_emit"

        @a2kit.read()
        async def fire_with_ctx(self, *, ctx: a2kit.ToolContext) -> dict[str, str]:
            captured_ctx.append(ctx)
            await ldd_event("fired-with-ctx", k=1)
            return {"ok": "with-ctx"}

        tools = (fire_with_ctx,)

    app = a2kit.AppBuilder("withctx").add_router(_WithCtxRouter()).build()

    async def go() -> None:
        async with client(app) as c:
            result = await c.invoke("fire_with_ctx")
            assert result == {"ok": "with-ctx"}
            assert any(e["name"] == "fired-with-ctx" for e in c.events)

    asyncio.run(go())
    assert len(captured_ctx) == 1
    assert captured_ctx[0] is not None
