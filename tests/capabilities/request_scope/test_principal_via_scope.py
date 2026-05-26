"""Capability: dispatch stage reads Principal via ``request_scope.get(Principal)``."""

from __future__ import annotations

from a2kit.packages.context import Principal
from a2kit.packages.context import request_scope


def test_published_principal_retrievable_by_type() -> None:
    p = Principal(subject="alice", scopes=frozenset({"read"}), claims={}, issued_by="test", raw_token=None)
    token = request_scope.publish(p)
    try:
        assert request_scope.get(Principal) is p
        assert request_scope.all_seeds() == {Principal: p}
    finally:
        request_scope.reset(token)
