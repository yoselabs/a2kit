"""Mirror unit tests for ``a2kit.packages.log.emission`` payload resolution."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from a2kit.packages.log.emission import _resolve


class _Color(Enum):
    RED = "red"


@dataclass
class _Pt:
    x: int
    y: int


class _Plain:
    def __init__(self) -> None:
        self.a = 1


def test_resolve_str_message_passes_fields_through() -> None:
    msg, fields = _resolve("hello", {"k": 1})
    assert msg == "hello"
    assert fields == {"k": 1}


def test_resolve_dataclass_dumps_with_enum_unwrapped() -> None:
    msg, fields = _resolve(_Pt(x=1, y=2), {})
    assert msg == "_Pt"
    assert fields == {"x": 1, "y": 2}


def test_resolve_enum_value_unwrapped() -> None:
    @dataclass
    class _Has:
        c: _Color

    _msg, fields = _resolve(_Has(c=_Color.RED), {})
    assert fields == {"c": "red"}


def test_resolve_plain_object_via_vars_then_merges_kwargs() -> None:
    msg, fields = _resolve(_Plain(), {"b": 2})
    assert msg == "_Plain"
    assert fields == {"a": 1, "b": 2}
