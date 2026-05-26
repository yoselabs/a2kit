"""BDD: `make_principal` test seam."""

from __future__ import annotations

from a2kit.packages.auth import make_principal


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
