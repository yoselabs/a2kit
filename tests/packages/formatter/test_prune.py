"""Mirror test for ``a2kit.packages.formatter.prune`` — pure-function unit tests.

End-to-end + cascade coverage lives in
``tests/capabilities/type_driven_format_routing/test_prune_empty.py``.
This file mirrors the source module per ``A2K-TEST-MIRROR`` and covers
the private helpers + ``PruneEmpty`` base class directly.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel

from a2kit.packages.formatter.prune import (
    PruneEmpty,
    _is_empty,
    dump_model_for_wire,
    prune_dict,
)


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


def test_prune_empty_base_drops_on_model_dump() -> None:
    class M(PruneEmpty):
        a: str
        b: str | None = None
        c: list[str] = []

    assert M(a="x").model_dump() == {"a": "x"}


def test_plain_basemodel_unaffected() -> None:
    class M(BaseModel):
        a: str
        b: str | None = None

    assert M(a="x").model_dump() == {"a": "x", "b": None}


def test_dump_model_for_wire_uses_native_serializer() -> None:
    class M(PruneEmpty):
        a: str
        b: str | None = None

    assert dump_model_for_wire(M(a="x")) == {"a": "x"}


def test_prune_empty_cascades_into_nested() -> None:
    class Inner(PruneEmpty):
        name: str
        note: str | None = None

    class Outer(BaseModel):
        inner: Inner

    assert Outer(inner=Inner(name="n", note=None)).model_dump() == {"inner": {"name": "n"}}
