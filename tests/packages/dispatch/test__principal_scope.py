"""Substrate-internal Principal seeding helper.

The helper isolates the read of the substrate-published Principal so
stages.py satisfies the ``principal-single-source`` grep gate while the
substrate adapters keep their ambient-context implementation private to
the dispatch layer.
"""

from __future__ import annotations

from a2kit.packages.context import Principal, _a2kit_request_principal
from a2kit.packages.dispatch._principal_scope import (
    current_request_principal,
    seed_principal_into_wire,
)


def test_current_request_principal_is_none_outside_a_request() -> None:
    assert current_request_principal() is None


def test_current_request_principal_reads_substrate_contextvar() -> None:
    p = Principal(subject="alice", scopes=frozenset(), claims={}, issued_by="t", raw_token=None)
    token = _a2kit_request_principal.set(p)
    try:
        assert current_request_principal() is p
    finally:
        _a2kit_request_principal.reset(token)


def test_seed_principal_into_wire_is_a_noop_without_a_principal() -> None:
    wire: dict = {}
    seed_principal_into_wire(wire)
    assert wire == {}


def test_seed_principal_into_wire_places_principal_under_the_internal_key() -> None:
    p = Principal(subject="alice", scopes=frozenset(), claims={}, issued_by="t", raw_token=None)
    token = _a2kit_request_principal.set(p)
    try:
        wire: dict = {}
        seed_principal_into_wire(wire)
        assert wire == {"_a2kit_principal": p}
    finally:
        _a2kit_request_principal.reset(token)


def test_seed_principal_into_wire_does_not_clobber_existing_seed() -> None:
    """``setdefault`` semantics — substrate-set wire kwargs win."""
    p_ctx = Principal(subject="alice", scopes=frozenset(), claims={}, issued_by="t", raw_token=None)
    p_explicit = Principal(subject="bob", scopes=frozenset(), claims={}, issued_by="t", raw_token=None)
    token = _a2kit_request_principal.set(p_ctx)
    try:
        wire = {"_a2kit_principal": p_explicit}
        seed_principal_into_wire(wire)
        assert wire["_a2kit_principal"] is p_explicit
    finally:
        _a2kit_request_principal.reset(token)
