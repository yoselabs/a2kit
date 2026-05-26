"""Capability: ``reset(token)`` clears every value the publish set."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from a2kit.packages.context import request_scope


@dataclass
class _A:
    n: int = 0


@dataclass
class _B:
    s: str = ""


def test_reset_clears_every_published_value() -> None:
    token = request_scope.publish(_A(n=1), _B(s="two"))
    request_scope.reset(token)
    with pytest.raises(request_scope.RequestScopeMissing):
        request_scope.get(_A)
    with pytest.raises(request_scope.RequestScopeMissing):
        request_scope.get(_B)
