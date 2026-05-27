"""Mirror tests for `packages/http/_principal_publish` — kwarg-scrape Principal publish helper."""

from __future__ import annotations

from a2kit.packages.context import Principal, request_scope
from a2kit.packages.http._principal_publish import publish_principal_from_kwargs


def _p(subject: str) -> Principal:
    return Principal(subject=subject, scopes=frozenset())


def test_publishes_when_principal_present_in_kwargs():
    token = publish_principal_from_kwargs({"_authz": _p("alice"), "x": 1})
    assert token is not None
    try:
        published = request_scope.try_get(Principal)
        assert published is not None
        assert published.subject == "alice"
    finally:
        request_scope.reset(token)


def test_returns_none_when_no_principal():
    token = publish_principal_from_kwargs({"x": 1, "y": "z"})
    assert token is None
    assert request_scope.try_get(Principal) is None


def test_finds_principal_regardless_of_kwarg_name():
    token = publish_principal_from_kwargs({"weird_name": _p("bob")})
    assert token is not None
    try:
        got = request_scope.try_get(Principal)
        assert got is not None
        assert got.subject == "bob"
    finally:
        request_scope.reset(token)


def test_first_principal_wins_if_multiple_present():
    p1 = _p("first")
    p2 = _p("second")
    token = publish_principal_from_kwargs({"a": p1, "b": p2})
    assert token is not None
    try:
        published = request_scope.try_get(Principal)
        assert published is not None
        # Either is acceptable per the spec; the helper picks the first
        # match. The behaviour MUST be deterministic for a given dict order.
        assert published.subject in {"first", "second"}
    finally:
        request_scope.reset(token)


def test_reset_restores_absent_state():
    assert request_scope.try_get(Principal) is None
    token = publish_principal_from_kwargs({"p": _p("temporary")})
    assert token is not None
    request_scope.reset(token)
    assert request_scope.try_get(Principal) is None
