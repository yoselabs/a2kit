"""Capability: LDD primitives work inside a scope; outside, they raise typed."""

from __future__ import annotations

import pytest

from a2kit.exceptions import AmbientContextMissing
from a2kit.packages.context import request_scope
from a2kit.packages.ldd.ambient import _LddState, _require_ambient_state, ldd_state_for_call
from a2kit.packages.testing.null_context import null_context


def test_ldd_state_retrievable_via_scope() -> None:
    with ldd_state_for_call(ctx=null_context()):
        state = request_scope.get(_LddState)
        assert state.ctx is not None


def test_ldd_primitive_outside_scope_raises_typed() -> None:
    with pytest.raises(AmbientContextMissing) as info:
        _require_ambient_state("event")
    # The shim subclass message is preserved; the __cause__ chains
    # from the underlying RequestScopeMissing.
    assert "event" in str(info.value)
    cause = info.value.__cause__
    assert isinstance(cause, request_scope.RequestScopeMissing)
    assert cause.requested_type is _LddState
