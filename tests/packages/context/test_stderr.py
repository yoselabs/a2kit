"""``StderrToolContext`` emits ``[ +s.mmm LEVEL] msg key=val`` lines to stderr.

Wire format: relative elapsed timestamps from context construction, formatted
as ``+s.mmm`` with three-decimal-place seconds. The stub's logging methods
(``info``/``warning``/``error``/``debug``/``log``) are async to match
``fastmcp.Context``'s public surface. Framework emission lives on
``a2kit.log.*`` (routed through stdlib handlers, not the ctx stub).
"""

from __future__ import annotations

import asyncio
import io
import re
import sys
from collections.abc import Awaitable, Callable
from typing import Any

import pytest

from a2kit.packages.context import MCPOnlyError, StderrToolContext


def _capture_stderr_async(awaitable_factory: Callable[[], Awaitable[Any]]) -> str:
    buf = io.StringIO()
    saved = sys.stderr
    sys.stderr = buf
    try:
        asyncio.run(awaitable_factory())  # ty: ignore[invalid-argument-type]  # why: ty's narrowed parameter type rejects this call; runtime accepts duck-typed/stub argument
    finally:
        sys.stderr = saved
    return buf.getvalue()


_PREFIX = re.compile(r"^\[ \+\s*\d+\.\d{3} \w+\s*]")


def test_info_no_fields_emits_prefix_and_msg() -> None:
    ctx = StderrToolContext()
    out = _capture_stderr_async(lambda: ctx.info("hello"))
    assert _PREFIX.match(out)
    assert "INFO" in out
    assert " hello" in out


def test_warning_with_extra_emits_kv() -> None:
    """Narrow stub matches fastmcp.Context: fields arrive via ``extra=``,
    not as ``**kwargs``. Field-bearing kwargs form moved to ``a2kit.log.warning``."""
    ctx = StderrToolContext()
    out = _capture_stderr_async(lambda: ctx.warning("stuck", extra={"retry": 3, "where": "foo"}))
    assert "WARN" in out
    assert "stuck" in out
    assert "retry=3" in out
    assert "where='foo'" in out


def test_error_with_extra_repr_quotes_strings_only() -> None:
    ctx = StderrToolContext()
    out = _capture_stderr_async(lambda: ctx.error("boom", extra={"code": 42, "name": "db"}))
    assert "code=42" in out
    assert "name='db'" in out


def test_debug_emits_debug_level() -> None:
    ctx = StderrToolContext()
    out = _capture_stderr_async(lambda: ctx.debug("internal"))
    assert "DEBUG" in out
    assert "internal" in out


def test_report_progress_uses_progress_level() -> None:
    ctx = StderrToolContext()
    out = _capture_stderr_async(lambda: ctx.report_progress(5, total=10))
    assert "progress" in out
    assert "current=5" in out
    assert "total=10" in out


def test_log_routes_to_emit() -> None:
    ctx = StderrToolContext()
    out = _capture_stderr_async(lambda: ctx.log("structured", level="warning", logger_name="x"))
    assert "WARN" in out
    assert "structured" in out
    assert "logger='x'" in out


def test_elapsed_timestamp_increments() -> None:
    import time

    ctx = StderrToolContext()
    out1 = _capture_stderr_async(lambda: ctx.info("first"))
    time.sleep(0.05)
    out2 = _capture_stderr_async(lambda: ctx.info("second"))
    e1 = float(out1.split("+")[1].split()[0])
    e2 = float(out2.split("+")[1].split()[0])
    assert e2 > e1


# --- State (per-instance dict) --- #


def test_state_round_trip() -> None:
    ctx = StderrToolContext()

    async def go() -> tuple[Any, Any]:
        await ctx.set_state("k", 42)
        v = await ctx.get_state("k")
        await ctx.delete_state("k")
        v2 = await ctx.get_state("k")
        return v, v2

    v, v2 = asyncio.run(go())
    assert v == 42
    assert v2 is None


def test_state_isolated_between_instances() -> None:
    a = StderrToolContext()
    b = StderrToolContext()

    async def go() -> Any:
        await a.set_state("x", 1)
        return await b.get_state("x")

    assert asyncio.run(go()) is None


# --- read_resource --- #


def test_read_resource_file_text(tmp_path: Any) -> None:
    """Returns a fastmcp-shaped result with ``.content`` attribute.

    Post ``align-context-method-signatures`` Treatment 1, the return
    mirrors fastmcp's ``ResourceResult``. The CLI stub uses
    ``_StubResourceResult`` (duck-typed, exposes ``.content``) to
    avoid eager ``mcp.types`` import.
    """
    p = tmp_path / "hello.txt"
    p.write_text("hello world", encoding="utf-8")
    ctx = StderrToolContext()
    result = asyncio.run(ctx.read_resource(f"file://{p}"))
    assert result.content == "hello world"


def test_read_resource_non_file_raises() -> None:
    ctx = StderrToolContext()
    with pytest.raises(MCPOnlyError):
        asyncio.run(ctx.read_resource("https://example.com/x"))


# --- elicit --- #


def test_elicit_accept_string(monkeypatch: Any) -> None:
    monkeypatch.setattr("builtins.input", lambda _prompt="": "alice")
    ctx = StderrToolContext()
    result = asyncio.run(ctx.elicit("name?", response_type=str))
    assert result.data == "alice"


def test_elicit_accept_int(monkeypatch: Any) -> None:
    monkeypatch.setattr("builtins.input", lambda _prompt="": "42")
    ctx = StderrToolContext()
    result = asyncio.run(ctx.elicit("count?", response_type=int))
    assert result.data == 42


def test_elicit_decline(monkeypatch: Any) -> None:
    monkeypatch.setattr("builtins.input", lambda _prompt="": "--decline")
    ctx = StderrToolContext()
    result = asyncio.run(ctx.elicit("?"))
    from fastmcp.server.elicitation import DeclinedElicitation

    assert isinstance(result, DeclinedElicitation)


def test_elicit_cancel_on_eof(monkeypatch: Any) -> None:
    def boom(_prompt: str = "") -> str:
        raise EOFError

    monkeypatch.setattr("builtins.input", boom)
    ctx = StderrToolContext()
    result = asyncio.run(ctx.elicit("?"))
    from fastmcp.server.elicitation import CancelledElicitation

    assert isinstance(result, CancelledElicitation)


def test_elicit_cancel_on_keyboard_interrupt(monkeypatch: Any) -> None:
    def boom(_prompt: str = "") -> str:
        raise KeyboardInterrupt

    monkeypatch.setattr("builtins.input", boom)
    ctx = StderrToolContext()
    result = asyncio.run(ctx.elicit("?"))
    from fastmcp.server.elicitation import CancelledElicitation

    assert isinstance(result, CancelledElicitation)


def test_elicit_accept_float(monkeypatch: Any) -> None:
    monkeypatch.setattr("builtins.input", lambda _prompt="": "3.14")
    ctx = StderrToolContext()
    result = asyncio.run(ctx.elicit("?", response_type=float))
    assert result.data == 3.14


def test_elicit_accept_bool(monkeypatch: Any) -> None:
    monkeypatch.setattr("builtins.input", lambda _prompt="": "yes")
    ctx = StderrToolContext()
    result = asyncio.run(ctx.elicit("?", response_type=bool))
    assert result.data is True


def test_elicit_enum_accept(monkeypatch: Any) -> None:
    monkeypatch.setattr("builtins.input", lambda _prompt="": "red")
    ctx = StderrToolContext()
    result = asyncio.run(ctx.elicit("?", response_type=["red", "blue"]))
    assert result.data == "red"


def test_elicit_enum_invalid_raises(monkeypatch: Any) -> None:
    monkeypatch.setattr("builtins.input", lambda _prompt="": "purple")
    ctx = StderrToolContext()
    with pytest.raises(MCPOnlyError):
        asyncio.run(ctx.elicit("?", response_type=["red", "blue"]))


def test_elicit_complex_type_raises(monkeypatch: Any) -> None:
    monkeypatch.setattr("builtins.input", lambda _prompt="": "x")

    class NestedSchema:
        pass

    ctx = StderrToolContext()
    with pytest.raises(MCPOnlyError):
        asyncio.run(ctx.elicit("?", response_type=NestedSchema))


def test_read_resource_binary(tmp_path: Any) -> None:
    p = tmp_path / "img.bin"
    p.write_bytes(b"\xff\xd8\xff\xe0")
    ctx = StderrToolContext()
    result = asyncio.run(ctx.read_resource(f"file://{p}"))
    assert result.content == b"\xff\xd8\xff\xe0"


def test_sample_step_raises() -> None:
    """Signature mirrors fastmcp's ``sample_step``; needs at least the
    ``messages`` positional argument (Treatment 2 of
    ``align-context-method-signatures``)."""
    ctx = StderrToolContext()
    with pytest.raises(MCPOnlyError):
        asyncio.run(ctx.sample_step("hello"))


# --- MCP-only methods raise --- #


@pytest.mark.parametrize(
    ("method", "args"),
    [
        ("sample", ("hi",)),
        ("list_resources", ()),
        ("list_prompts", ()),
        ("get_prompt", ("p",)),
        ("list_roots", ()),
        ("send_notification", (None,)),
    ],
)
def test_mcp_only_methods_raise(method: str, args: tuple[Any, ...]) -> None:
    ctx = StderrToolContext()
    fn = getattr(ctx, method)
    with pytest.raises(MCPOnlyError):
        asyncio.run(fn(*args))
