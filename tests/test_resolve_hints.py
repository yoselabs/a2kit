"""``a2kit.signature.resolve_hints`` warn-once dedup (Section 3.7)."""

from __future__ import annotations

import logging

import pytest

from a2kit.signature import _WARN_ONCE, resolve_hints


@pytest.fixture(autouse=True)
def _reset_warn_once() -> None:
    _WARN_ONCE.clear()


def test_resolve_hints_returns_empty_dict_on_failure(caplog: pytest.LogCaptureFixture) -> None:
    def fn(x: ThereIsNoSuchType) -> None:  # type: ignore[name-defined]  # noqa: F821, ARG001  # ty: ignore[unresolved-reference]  # why: annotation references a deliberately-undefined name to trigger get_type_hints failure
        ...

    with caplog.at_level(logging.WARNING, logger="a2kit.signature"):
        out = resolve_hints(fn)
    assert out == {}
    assert any("resolve_hints failed" in r.message for r in caplog.records)


def test_resolve_hints_warns_once_per_qualname(caplog: pytest.LogCaptureFixture) -> None:
    def fn(x: ThereIsNoSuchType) -> None:  # type: ignore[name-defined]  # noqa: F821, ARG001  # ty: ignore[unresolved-reference]  # why: annotation references a deliberately-undefined name to trigger get_type_hints failure
        ...

    with caplog.at_level(logging.WARNING, logger="a2kit.signature"):
        resolve_hints(fn)
        resolve_hints(fn)
        resolve_hints(fn)
    matches = [r for r in caplog.records if "resolve_hints failed" in r.message]
    assert len(matches) == 1, f"expected 1 WARN, got {len(matches)}"


def test_resolve_hints_resolves_normal_function() -> None:
    def fn(a: int, b: str) -> bool:  # noqa: ARG001
        return True

    out = resolve_hints(fn)
    assert out == {"a": int, "b": str, "return": bool}
