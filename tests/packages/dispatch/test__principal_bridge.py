"""``packages/dispatch/_principal_bridge.py`` — named writer/reader API.

Locks the contract: set/get symmetry, reset restores prior state,
nested set+reset semantics, reader is None outside a request.
"""

from __future__ import annotations

from a2kit.packages.context import Principal
from a2kit.packages.dispatch._principal_bridge import (
    current_request_principal,
    reset_request_principal,
    set_request_principal,
)


def _principal(name: str) -> Principal:
    return Principal(
        subject=name,
        scopes=frozenset(),
        claims={},
        issued_by="t",
        raw_token=None,
    )


def test_reader_returns_none_outside_a_request() -> None:
    assert current_request_principal() is None


def test_set_then_reader_returns_published_principal() -> None:
    p = _principal("alice")
    token = set_request_principal(p)
    try:
        assert current_request_principal() is p
    finally:
        reset_request_principal(token)
    assert current_request_principal() is None


def test_reset_restores_prior_state() -> None:
    """Nested set+reset returns to the outer value."""
    outer = _principal("outer")
    inner = _principal("inner")

    outer_token = set_request_principal(outer)
    try:
        assert current_request_principal() is outer
        inner_token = set_request_principal(inner)
        try:
            assert current_request_principal() is inner
        finally:
            reset_request_principal(inner_token)
        assert current_request_principal() is outer
    finally:
        reset_request_principal(outer_token)
    assert current_request_principal() is None


def test_module_does_not_export_raw_contextvar() -> None:
    """The ContextVar itself is module-private; only the named API is exported."""
    import a2kit.packages.dispatch._principal_bridge as bridge

    assert set(bridge.__all__) == {
        "current_request_principal",
        "reset_request_principal",
        "set_request_principal",
    }


def test_context_package_does_not_re_export_contextvar() -> None:
    """`packages/context` returns to type-only; no ambient state escapes L0."""
    import a2kit.packages.context as ctx_pkg

    assert "_a2kit_request_principal" not in ctx_pkg.__all__
    assert not hasattr(ctx_pkg, "_a2kit_request_principal")
