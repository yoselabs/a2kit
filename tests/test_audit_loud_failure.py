"""Regression tests for audit-loud-failure-discipline.

Covers the 5 audit findings (Pattern A silent fallbacks, Pattern B
defensive hasattr, Pattern C constructor kwarg guards) — each as a
narrow check that the post-cleanup behavior holds.
"""

from __future__ import annotations

import logging

import pytest

import a2kit


# --- Pattern A: silent fallback → WARN-then-degrade --- #


def test_compute_report_schema_logs_warn_on_failure(caplog: pytest.LogCaptureFixture) -> None:
    """Unschemable report type → returns None AND logs at WARN."""
    from a2kit.tool import _compute_report_schema

    class _Unschemable:
        """Bare class without pydantic schema support."""

    # Reset the warn-once cache so this test fires the warning fresh.
    from a2kit.tool import _WARN_ONCE_REPORT_SCHEMA

    _WARN_ONCE_REPORT_SCHEMA.discard(_Unschemable.__qualname__)

    with caplog.at_level(logging.WARNING, logger="a2kit"):
        result = _compute_report_schema(_Unschemable)

    assert result is None
    assert any("_compute_report_schema" in rec.message and "_Unschemable" in rec.message for rec in caplog.records)


def test_compute_report_schema_warn_dedupes(caplog: pytest.LogCaptureFixture) -> None:
    """Repeated failures on the same type warn exactly once."""
    from a2kit.tool import _WARN_ONCE_REPORT_SCHEMA, _compute_report_schema

    class _UnschemableDedupe:
        pass

    _WARN_ONCE_REPORT_SCHEMA.discard(_UnschemableDedupe.__qualname__)

    with caplog.at_level(logging.WARNING, logger="a2kit"):
        _compute_report_schema(_UnschemableDedupe)
        _compute_report_schema(_UnschemableDedupe)

    hits = [rec for rec in caplog.records if "_UnschemableDedupe" in rec.message]
    assert len(hits) == 1


# --- Pattern C: constructor kwarg guards --- #


def test_router_init_rejects_unknown_kwargs() -> None:
    """``Router.__init__`` raises TypeError on unexpected kwargs."""

    class _R(a2kit.Router):
        slug = "r"
        tools = ()

    with pytest.raises(TypeError) as ei:
        _R(totally_unknown=True)  # type: ignore[call-arg]
    msg = str(ei.value)
    assert "totally_unknown" in msg
