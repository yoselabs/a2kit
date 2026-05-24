"""BDD: `authenticated_as` / `make_principal` test seam.

Per `tool-authorization`: the context manager binds the contextvar on
enter and resets on exit, whether the block raised or not. The
`make_principal` factory mirrors the default Principal shape.
"""

from __future__ import annotations

import pytest

from a2kit.packages.auth import authenticated_as, make_principal
from a2kit.packages.context import _a2kit_request_principal


def test_make_principal_defaults() -> None:
    p = make_principal(subject="u1")
    assert p.subject == "u1"
    assert p.scopes == frozenset()
    assert p.claims == {}
    assert p.issued_by == "test"
    assert p.raw_token is None


def test_make_principal_with_scopes_and_claims() -> None:
    p = make_principal(subject="u1", scopes=["a", "b"], claims={"k": 1})
    assert p.scopes == frozenset({"a", "b"})
    assert p.claims == {"k": 1}


def test_authenticated_as_sets_and_resets_contextvar() -> None:
    assert _a2kit_request_principal.get() is None
    p = make_principal(subject="u1")
    with authenticated_as(p):
        assert _a2kit_request_principal.get() is p
    assert _a2kit_request_principal.get() is None


def test_authenticated_as_resets_on_exception() -> None:
    p = make_principal(subject="u1")
    with pytest.raises(RuntimeError, match="boom"), authenticated_as(p):
        raise RuntimeError("boom")
    assert _a2kit_request_principal.get() is None
