"""Unit tests for new exception classes introduced by
fix-mcp-dispatch-strips-ctx.

Mirror file per A2K-TEST-MIRROR — the consolidated exception tests
for older classes live alongside the consumers that raise them
(e.g. ``test_ambient_ldd_ctx.py``).
"""

from __future__ import annotations

import pytest

from a2kit.exceptions import (
    A2KitContextBindingBroken,
    A2KitError,
    A2KitInvalidContextAnnotation,
)


def test_mirror_stub_present() -> None:
    """Sentinel — proves the mirror file exists with a ``def test_*`` function."""


def test_context_binding_broken_carries_attrs_and_renders() -> None:
    exc = A2KitContextBindingBroken("R.ping", ctx_param_name="ctx")
    assert exc.fn_name == "R.ping"
    assert exc.ctx_param_name == "ctx"
    assert isinstance(exc, A2KitError)
    assert isinstance(exc, RuntimeError)
    msg = str(exc)
    assert "R.ping" in msg
    assert "'ctx'" in msg
    assert "wrapper-chain regression" in msg


def test_invalid_context_annotation_carries_attrs_and_renders() -> None:
    exc = A2KitInvalidContextAnnotation("R.bad", param_name="ctx", hint="drop '| None'.")
    assert exc.fn_name == "R.bad"
    assert exc.param_name == "ctx"
    assert exc.hint == "drop '| None'."
    assert isinstance(exc, A2KitError)
    assert isinstance(exc, TypeError)
    msg = str(exc)
    assert "R.bad" in msg
    assert "'ctx'" in msg
    assert "drop '| None'." in msg


def test_raise_and_catch_via_base() -> None:
    """Both classes are catchable via ``A2KitError`` and their Python parents."""
    with pytest.raises(A2KitError):
        raise A2KitContextBindingBroken("f", ctx_param_name="ctx")
    with pytest.raises(RuntimeError):
        raise A2KitContextBindingBroken("f", ctx_param_name="ctx")
    with pytest.raises(A2KitError):
        raise A2KitInvalidContextAnnotation("f", param_name="ctx", hint="h")
    with pytest.raises(TypeError):
        raise A2KitInvalidContextAnnotation("f", param_name="ctx", hint="h")
