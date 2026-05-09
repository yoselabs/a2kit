"""StderrToolContext emits compact ``[LEVEL] msg key=val`` lines to stderr."""

from __future__ import annotations

import asyncio
import io
import sys

from a2kit.packages.cli.context import StderrToolContext


def _capture_stderr(callable_, *args, **kwargs) -> str:
    buf = io.StringIO()
    saved = sys.stderr
    sys.stderr = buf
    try:
        callable_(*args, **kwargs)
    finally:
        sys.stderr = saved
    return buf.getvalue()


def test_info_no_fields_emits_level_and_msg() -> None:
    ctx = StderrToolContext()
    out = _capture_stderr(ctx.info, "hello")
    assert out == "[INFO] hello\n"


def test_warning_with_fields_emits_kv() -> None:
    ctx = StderrToolContext()
    out = _capture_stderr(ctx.warning, "stuck", retry=3, where="foo")
    assert out.startswith("[WARN] stuck ")
    assert "retry=3" in out
    assert "where='foo'" in out


def test_error_repr_quotes_strings_only() -> None:
    ctx = StderrToolContext()
    out = _capture_stderr(ctx.error, "boom", code=42, name="db")
    assert "code=42" in out
    assert "name='db'" in out


def test_debug_emits_debug_level() -> None:
    ctx = StderrToolContext()
    out = _capture_stderr(ctx.debug, "internal")
    assert out == "[INFO] internal\n".replace("INFO", "DEBUG")


def test_report_progress_uses_info_level() -> None:
    ctx = StderrToolContext()

    def go() -> None:
        asyncio.run(ctx.report_progress(5, total=10))

    out = _capture_stderr(go)
    assert out.startswith("[INFO] progress ")
    assert "current=5" in out
    assert "total=10" in out


def test_satisfies_toolcontext_protocol() -> None:
    from a2kit.runtime import ToolContext

    assert isinstance(StderrToolContext(), ToolContext)
