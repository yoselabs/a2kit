"""BDD: `Principal` frozen dataclass + lazy top-level re-export (add-principal-type)."""

from __future__ import annotations

import dataclasses
import subprocess
import sys

import pytest


class TestPrincipalShape:
    def test_construction_with_all_fields(self) -> None:
        from a2kit.packages.context import Principal

        p = Principal(
            subject="u1",
            scopes=frozenset({"read", "write"}),
            claims={"email": "u1@example.com"},
            issued_by="test",
            raw_token="abc",
        )
        assert p.subject == "u1"
        assert p.scopes == frozenset({"read", "write"})
        assert p.claims == {"email": "u1@example.com"}
        assert p.issued_by == "test"
        assert p.raw_token == "abc"

    def test_raw_token_defaults_to_none(self) -> None:
        from a2kit.packages.context import Principal

        p = Principal(subject="u1", scopes=frozenset(), claims={}, issued_by="test")
        assert p.raw_token is None

    def test_frozen(self) -> None:
        from a2kit.packages.context import Principal

        p = Principal(subject="u1", scopes=frozenset(), claims={}, issued_by="test")
        with pytest.raises(dataclasses.FrozenInstanceError):
            p.subject = "u2"  # type: ignore[misc]  # ty: ignore[invalid-assignment]  # why: deliberately exercises frozen-dataclass invariant

    def test_equality_by_fields(self) -> None:
        from a2kit.packages.context import Principal

        a = Principal(subject="u1", scopes=frozenset({"r"}), claims={"a": 1}, issued_by="t")
        b = Principal(subject="u1", scopes=frozenset({"r"}), claims={"a": 1}, issued_by="t")
        c = Principal(subject="u2", scopes=frozenset({"r"}), claims={"a": 1}, issued_by="t")
        assert a == b
        assert a != c

    def test_claims_accepts_any_mapping(self) -> None:
        from types import MappingProxyType

        from a2kit.packages.context import Principal

        p = Principal(
            subject="u1",
            scopes=frozenset(),
            claims=MappingProxyType({"k": "v"}),
            issued_by="test",
        )
        assert p.claims["k"] == "v"


class TestPrincipalTopLevelLazyReExport:
    def test_principal_resolves_to_packages_context_principal(self) -> None:
        import a2kit
        from a2kit.packages.context import Principal as Canonical

        assert a2kit.Principal is Canonical

    def test_principal_is_lazy_at_top_level(self) -> None:
        # Sub-process so the cold-start invariant is observable without
        # mutating sys.modules and destabilising sibling tests.
        code = (
            "import a2kit, json, sys; "
            "in_dict = 'Principal' in a2kit.__dict__; "
            "ctx_loaded = 'a2kit.packages.context.principal' in sys.modules; "
            "print(json.dumps({'in_dict': in_dict, 'ctx_loaded': ctx_loaded}))"
        )
        out = subprocess.check_output([sys.executable, "-c", code], text=True).strip()
        import json

        result = json.loads(out)
        assert result["in_dict"] is False
        assert result["ctx_loaded"] is False
