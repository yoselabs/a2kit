"""Mirror test for ``a2kit.packages.formatter.prune`` — pure-function unit tests.

End-to-end + scenario coverage lives in
``tests/capabilities/type_driven_format_routing/test_prune_empty.py``.
This file mirrors the source module per ``A2K-TEST-MIRROR`` and covers
the private helpers directly.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from a2kit.packages.formatter.prune import (
    PRUNE_EMPTY_KEY,
    _is_empty,
    dump_model_for_wire,
    model_wants_prune,
    prune_dict,
    prune_empty,
)


def test_prune_empty_returns_marker_dict() -> None:
    assert prune_empty() == {PRUNE_EMPTY_KEY: True}


def test_is_empty_matrix() -> None:
    assert _is_empty(None)
    assert _is_empty("")
    assert _is_empty([])
    assert _is_empty({})
    assert not _is_empty(0)
    assert not _is_empty(False)  # noqa: FBT003 -- testing _is_empty's handling of bare False (not a function flag)
    assert not _is_empty(Decimal(0))
    assert not _is_empty("x")
    assert not _is_empty([0])
    assert not _is_empty({"k": None})


def test_prune_dict_drops_empties() -> None:
    payload = {"a": "x", "b": None, "c": [], "d": {}, "e": 0}
    assert prune_dict(payload) == {"a": "x", "e": 0}


def test_model_wants_prune_true_when_marked() -> None:
    class M(BaseModel):
        model_config = ConfigDict(**prune_empty())
        x: int

    assert model_wants_prune(M(x=1)) is True
    assert model_wants_prune(M) is True


def test_model_wants_prune_false_by_default() -> None:
    class M(BaseModel):
        x: int

    assert model_wants_prune(M(x=1)) is False


def test_dump_model_for_wire_prunes_when_marked() -> None:
    class M(BaseModel):
        model_config = ConfigDict(**prune_empty())
        a: str
        b: str | None = None

    assert dump_model_for_wire(M(a="x")) == {"a": "x"}


def test_dump_model_for_wire_preserves_when_unmarked() -> None:
    class M(BaseModel):
        a: str
        b: str | None = None

    assert dump_model_for_wire(M(a="x")) == {"a": "x", "b": None}
