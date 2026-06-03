"""Mirror unit tests for ``a2kit.packages.log.scope``."""

from __future__ import annotations

from a2kit.packages.log.scope import _active_scope, _CallScope, _elapsed_ms, bind_call_scope
from a2kit.packages.testing.null_context import null_context


def test_active_scope_is_none_outside_dispatch() -> None:
    assert _active_scope() is None


def test_bind_call_scope_publishes_and_clears() -> None:
    with bind_call_scope(ctx=null_context(), call_id="c1", tool_name="t"):
        scope = _active_scope()
        assert scope is not None
        assert scope.call_id == "c1"
        assert scope.tool_name == "t"
    assert _active_scope() is None


def test_elapsed_ms_is_non_negative_int() -> None:
    scope = _CallScope(ctx=null_context())
    assert isinstance(_elapsed_ms(scope), int)
    assert _elapsed_ms(scope) >= 0
