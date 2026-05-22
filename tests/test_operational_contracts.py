"""Section 7 of `a2web-feedback-round-2`: operational contracts regressions.

Each test pins down one behavior documented in `OPERATIONAL_CONTRACTS.md`:

  Scenario Q1: cancellation propagates through the dispatcher to the tool body
  Scenario Q3: two App instances have isolated singletons + lifecycle handlers
  Scenario Q5a: unhandled exceptions reach the caller (no swallow)
  Scenario Q5b: App(debug=True) toggles traceback exposure (flag-only test —
                full MCP envelope shape is out of scope here)
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

import a2kit
from a2kit.testing import client, peek


# --- Q1: cancellation propagates --- #


def test_cancellation_propagates_to_tool_body() -> None:
    """A tool body cancelled mid-await sees CancelledError; finally runs."""
    cleanup_ran: list[bool] = []

    class _R(a2kit.Router):
        slug = "_r"

        @a2kit.read()
        async def slow(self) -> dict:
            try:
                await asyncio.sleep(60)
                return {"never": True}
            except asyncio.CancelledError:
                cleanup_ran.append(True)
                raise

        tools = (slow,)

    app = a2kit.App("cancel").add_router(_R())

    async def go() -> None:
        async with client(app) as c:
            task = asyncio.create_task(c.invoke("slow"))
            await asyncio.sleep(0.05)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

    asyncio.run(go())
    assert cleanup_ran == [True], "tool body's `except CancelledError:` block did not run"


# --- Q3: multi-App isolation --- #


class _AppState:
    def __init__(self, label: str) -> None:
        self.label = label


def test_two_apps_have_isolated_singletons() -> None:
    """Each App keeps its own singleton cache; resolving the same type yields different instances."""
    app_a = a2kit.App("a")
    app_b = a2kit.App("b")
    app_a.provide(_AppState, lambda: _AppState("from-a"))
    app_b.provide(_AppState, lambda: _AppState("from-b"))

    state_a = peek(app_a, _AppState)
    state_b = peek(app_b, _AppState)
    assert state_a.label == "from-a"
    assert state_b.label == "from-b"
    assert state_a is not state_b


# --- Q5: error envelope --- #


def test_unhandled_exception_bubbles_through_dispatcher() -> None:
    """The dispatcher does not swallow tool exceptions — they reach the caller.

    Post ``rebuild-test-client-on-real-context`` the test client runs
    through the real MCP transport, so exceptions surface as
    ``fastmcp.exceptions.ToolError`` carrying the a2kit-owned envelope
    from ``mcp-structured-wire-error-envelope``. The Python exception
    class round-trips via the JSON payload.
    """
    import json as _json

    from fastmcp.exceptions import ToolError

    class _R(a2kit.Router):
        slug = "_r"

        @a2kit.read()
        async def boom(self) -> dict:
            raise ValueError("explicit failure")

        tools = (boom,)

    app = a2kit.App("err").add_router(_R())

    async def go() -> Any:
        async with client(app) as c:
            return await c.invoke("boom")

    with pytest.raises(ToolError) as ei:
        asyncio.run(go())
    payload = _json.loads(str(ei.value))
    assert payload["class"] == "ValueError"
    assert payload["message"] == "explicit failure"


def test_app_debug_flag_defaults_false() -> None:
    """`App.debug` defaults False; explicit `debug=True` flips."""
    plain = a2kit.App("plain")
    assert plain.debug is False
    chatty = a2kit.App("chatty", debug=True)
    assert chatty.debug is True


def test_cli_error_no_traceback_when_debug_false() -> None:
    """CLI error path prints `error: ...` but no traceback when debug=False."""
    from click.testing import CliRunner

    from a2kit.packages.cli.builder import build_full_cli

    class _R(a2kit.Router):
        slug = "_r"

        @a2kit.read()
        async def boom(self) -> dict:
            raise ValueError("plain failure")

        tools = (boom,)

    app = a2kit.App("cli-err").add_router(_R())
    cli = build_full_cli(app)
    result = CliRunner().invoke(cli, ["_r", "boom"])
    assert result.exit_code != 0
    assert "error: plain failure" in result.output
    assert "Traceback (most recent call last):" not in result.output


def test_cli_error_includes_traceback_when_debug_true() -> None:
    """CLI error path prints the traceback to stderr when debug=True."""
    from click.testing import CliRunner

    from a2kit.packages.cli.builder import build_full_cli

    class _R(a2kit.Router):
        slug = "_r"

        @a2kit.read()
        async def boom(self) -> dict:
            raise ValueError("detailed failure")

        tools = (boom,)

    app = a2kit.App("cli-err-dbg", debug=True).add_router(_R())
    cli = build_full_cli(app)
    result = CliRunner().invoke(cli, ["_r", "boom"])
    assert result.exit_code != 0
    assert "error: detailed failure" in result.output
    assert "Traceback" in result.output
    # The actual ValueError frame should appear.
    assert "ValueError" in result.output


def test_mcp_error_envelope_wraps_message_with_class_and_message() -> None:
    """A captured tool-body error renders as ``ToolError(json.dumps(...))``.

    ``ErrorCaptureStage`` (transport-neutral) captures the exception;
    the MCP ``McpErrorRenderStage`` renders it. The envelope owns the
    wire bytes independently of FastMCP's ``mask_error_details`` per
    `mcp-structured-wire-error-envelope`.
    """
    import asyncio
    import json

    from fastmcp.exceptions import ToolError

    import a2kit
    from a2kit.packages.dispatch import ErrorCaptureStage, ToolBuildSpec
    from a2kit.packages.mcp._wrappers import McpErrorRenderStage

    async def boom() -> None:
        raise ValueError("base msg")

    spec = ToolBuildSpec(app=a2kit.App("oc-err", debug=True), router=None, meta=None)
    wrapped = ErrorCaptureStage().wrap(boom, spec)
    wrapped = McpErrorRenderStage().wrap(wrapped, spec)

    with pytest.raises(ToolError) as ei:
        asyncio.run(wrapped())
    payload = json.loads(str(ei.value))
    assert payload["class"] == "ValueError"
    assert payload["message"] == "base msg"
    assert "traceback" in payload
    assert "ValueError: base msg" in payload["traceback"]


def test_mcp_error_envelope_passes_cancelled_unchanged() -> None:
    """CancelledError must not be wrapped (per OPERATIONAL_CONTRACTS Q1)."""
    import asyncio

    import a2kit
    from a2kit.packages.dispatch import ErrorCaptureStage, ToolBuildSpec
    from a2kit.packages.mcp._wrappers import McpErrorRenderStage

    async def stuck() -> None:
        await asyncio.sleep(60)

    spec = ToolBuildSpec(app=a2kit.App("oc-cancel"), router=None, meta=None)
    wrapped = ErrorCaptureStage().wrap(stuck, spec)
    wrapped = McpErrorRenderStage().wrap(wrapped, spec)

    async def go() -> None:
        task = asyncio.create_task(wrapped())
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(go())


def test_mcp_server_passes_mask_error_details_from_app_debug() -> None:
    """`App(debug=True)` flips fastmcp's mask_error_details to False."""
    from a2kit.packages.mcp.server import build_mcp_server

    plain = a2kit.App("plain")
    server_plain = build_mcp_server(plain)
    assert server_plain._mask_error_details is True

    chatty = a2kit.App("chatty", debug=True)
    server_chatty = build_mcp_server(chatty)
    assert server_chatty._mask_error_details is False
