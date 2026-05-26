"""Capability: ``get(T)`` with no prior publish raises ``RequestScopeMissing(T)``."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from a2kit.packages.context import request_scope


@dataclass
class _Marker:
    name: str = ""


def test_get_missing_raises_request_scope_missing() -> None:
    with pytest.raises(request_scope.RequestScopeMissing) as info:
        request_scope.get(_Marker)
    assert info.value.requested_type is _Marker
    assert "_Marker" in str(info.value)
    assert "substrate" in str(info.value).lower()
