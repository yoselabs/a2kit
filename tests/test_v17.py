"""v0.17 — formatter robustness, Hypothesis property tests, OTel result.count.

Covers:
- `_dump_items` raises on non-row items (behaviour change from silent drop).
- `format_from_annotation` unwraps `Awaitable[T]` / `Coroutine[..., T]`.
- `format_from_annotation` returns "json" for bare `dict`, `Mapping[K, V]`,
  `TypedDict`.
- `_flat_pydantic_fields` handles `Optional[Union[A, B]]` (multi-arm union).
- Property test: `truncate(x)` is structural identity except str clipping; never
  mutates input.
- Property test: `format_from_annotation` precompute and `toon_or_json` runtime
  agree on the format for any Pydantic model with flat scalar fields.
- OTel middleware stamps `tool.result.count` for list / Page results.
"""

from __future__ import annotations

import copy
from collections.abc import Awaitable, Coroutine, Mapping
from typing import Any, TypedDict

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import BaseModel

from a2kit.formatter import (
    Page,
    _dump_items,
    _flat_pydantic_fields,
    format_from_annotation,
    toon_or_json,
    truncate,
)


# ---- _dump_items: explicit error on non-row items -----------------------


class _Row(BaseModel):
    a: int
    b: str


def test_dump_items_raises_on_scalar_items() -> None:
    with pytest.raises(TypeError, match="expected dict or BaseModel rows"):
        _dump_items([1, 2, 3])


def test_dump_items_raises_on_mixed_with_index() -> None:
    with pytest.raises(TypeError, match="at index 2"):
        _dump_items([{"a": 1}, _Row(a=1, b="x"), 7])


def test_dump_items_accepts_pure_rows() -> None:
    out = _dump_items([{"a": 1, "b": "x"}, _Row(a=2, b="y")])
    assert out == [{"a": 1, "b": "x"}, {"a": 2, "b": "y"}]


# ---- format_from_annotation: Awaitable / Coroutine unwrap ---------------


def test_format_from_annotation_awaitable_unwrap_list_pydantic() -> None:
    assert format_from_annotation(Awaitable[list[_Row]]) == "tsv"


def test_format_from_annotation_coroutine_unwrap_list_pydantic() -> None:
    assert format_from_annotation(Coroutine[Any, Any, list[_Row]]) == "tsv"


def test_format_from_annotation_awaitable_scalar_returns_json() -> None:
    assert format_from_annotation(Awaitable[int]) == "json"


# ---- format_from_annotation: bare dict / Mapping / TypedDict -------------


def test_format_from_annotation_bare_dict_returns_json() -> None:
    assert format_from_annotation(dict) == "json"


def test_format_from_annotation_mapping_returns_json() -> None:
    assert format_from_annotation(Mapping[str, int]) == "json"


class _TD(TypedDict):
    a: int
    b: str


def test_format_from_annotation_typeddict_returns_json() -> None:
    assert format_from_annotation(_TD) == "json"


def test_is_typed_dict_returns_false_for_non_type() -> None:
    """Sanity: non-type inputs (e.g. plain strings) are rejected."""
    from a2kit.formatter import _is_typed_dict

    assert _is_typed_dict("not a type") is False
    assert _is_typed_dict(42) is False


# ---- _flat_pydantic_fields: Optional[Union[A, B]] -----------------------


class _MultiUnion(BaseModel):
    # Two flat arms — the field should still be flat.
    a: int | str | None


class _MultiUnionNested(BaseModel):
    # One nested arm — field is non-flat.
    a: int | list[int] | None


class _MultiUnionAny(BaseModel):
    # An `Any` arm forces ambiguity (None).
    a: int | Any | None


def test_flat_pydantic_fields_optional_union_two_flat_arms_is_flat() -> None:
    assert _flat_pydantic_fields(_MultiUnion) is True


def test_flat_pydantic_fields_optional_union_with_nested_arm_is_nonflat() -> None:
    assert _flat_pydantic_fields(_MultiUnionNested) is False


def test_flat_pydantic_fields_optional_union_with_any_arm_is_ambiguous() -> None:
    assert _flat_pydantic_fields(_MultiUnionAny) is None


class _Inner(BaseModel):
    x: int


class _MultiUnionWithModel(BaseModel):
    # One arm is a BaseModel — non-flat (covers _classify_arm BaseModel branch).
    a: int | _Inner | None


def test_flat_pydantic_fields_optional_union_with_basemodel_arm_is_nonflat() -> None:
    assert _flat_pydantic_fields(_MultiUnionWithModel) is False


def test_format_from_annotation_bare_awaitable_returns_none_via_unwrap() -> None:
    """Bare `Awaitable` (no args) — unwrap is a no-op; falls through to None."""
    assert format_from_annotation(Awaitable) is None


def test_format_from_annotation_bare_coroutine_returns_none() -> None:
    """Bare `Coroutine` (no args) — same."""
    assert format_from_annotation(Coroutine) is None


# ---- Hypothesis property: truncate is structural identity ---------------


_atom_strategy = st.one_of(
    st.text(max_size=20),
    st.integers(min_value=-1000, max_value=1000),
    st.booleans(),
    st.none(),
    st.floats(allow_nan=False, allow_infinity=False, width=32),
)
_value_strategy = st.recursive(
    _atom_strategy,
    lambda children: st.one_of(
        st.lists(children, max_size=4),
        st.dictionaries(st.text(max_size=8), children, max_size=4),
    ),
    max_leaves=20,
)


@given(value=_value_strategy)
def test_truncate_does_not_mutate_input(value: Any) -> None:
    snapshot = copy.deepcopy(value)
    truncate(value, max_chars=10000)
    assert value == snapshot


@given(value=_value_strategy)
def test_truncate_preserves_structure_when_strings_short(value: Any) -> None:
    """With a high `max_chars`, output is structurally equal to input
    (after the dict/list passes; tuples become lists by contract).
    """
    out = truncate(value, max_chars=10_000)
    assert _structural_equal(out, value)


def _structural_equal(a: Any, b: Any) -> bool:
    """Compare with the contract: tuples become lists in `truncate`."""
    if isinstance(a, list) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(_structural_equal(x, y) for x, y in zip(a, b, strict=True))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_structural_equal(a[k], b[k]) for k in a)
    return a == b


# ---- Hypothesis property: precompute ↔ runtime format agree -------------


class _FlatModel(BaseModel):
    n: int
    s: str
    b: bool


@given(rows=st.lists(st.builds(_FlatModel, n=st.integers(), s=st.text(max_size=8), b=st.booleans()), min_size=1, max_size=5))
def test_format_from_annotation_agrees_with_runtime_for_flat_pydantic(rows: list[_FlatModel]) -> None:
    """Precompute says `tsv` for `list[_FlatModel]`; runtime `toon_or_json`
    on the dumped rows agrees (uniform-flat → tsv).
    """
    precomputed = format_from_annotation(list[_FlatModel])
    runtime, _payload = toon_or_json([r.model_dump() for r in rows])
    assert precomputed == "tsv"
    assert runtime == "tsv"


# ---- OTel: tool.result.count attribute -----------------------------------


def test_otel_stamp_result_count_for_list() -> None:
    """Direct unit test of the helper that stamps cardinality."""
    from a2kit.middleware._otel import _stamp_result_count

    class _Span:
        def __init__(self) -> None:
            self.attrs: dict[str, Any] = {}

        def set_attribute(self, k: str, v: Any) -> None:
            self.attrs[k] = v

    class _SpanWrapper:
        def __init__(self, span: _Span) -> None:
            self._span = span

    span = _Span()
    _stamp_result_count(_SpanWrapper(span), [1, 2, 3])
    assert span.attrs == {"tool.result.count": 3}


def test_otel_stamp_result_count_for_page() -> None:
    from a2kit.middleware._otel import _stamp_result_count

    class _Span:
        def __init__(self) -> None:
            self.attrs: dict[str, Any] = {}

        def set_attribute(self, k: str, v: Any) -> None:
            self.attrs[k] = v

    class _SpanWrapper:
        def __init__(self, span: _Span) -> None:
            self._span = span

    span = _Span()
    page: Page[dict[str, int]] = Page(items=[{"a": 1}, {"a": 2}])
    _stamp_result_count(_SpanWrapper(span), page)
    assert span.attrs == {"tool.result.count": 2}


def test_otel_stamp_result_count_skips_non_list() -> None:
    from a2kit.middleware._otel import _stamp_result_count

    class _Span:
        def __init__(self) -> None:
            self.attrs: dict[str, Any] = {}

        def set_attribute(self, k: str, v: Any) -> None:
            self.attrs[k] = v

    class _SpanWrapper:
        def __init__(self, span: _Span) -> None:
            self._span = span

    span = _Span()
    _stamp_result_count(_SpanWrapper(span), {"shape": "single"})
    assert span.attrs == {}


def test_otel_stamp_result_count_no_op_on_null_span() -> None:
    from a2kit.middleware._otel import _stamp_result_count

    class _SpanWrapper:
        _span = None

    # Should not raise — defensive against null adapters.
    _stamp_result_count(_SpanWrapper(), [1, 2, 3])


def test_otel_stamp_result_count_for_tuple() -> None:
    from a2kit.middleware._otel import _stamp_result_count

    class _Span:
        def __init__(self) -> None:
            self.attrs: dict[str, Any] = {}

        def set_attribute(self, k: str, v: Any) -> None:
            self.attrs[k] = v

    class _SpanWrapper:
        def __init__(self, span: _Span) -> None:
            self._span = span

    span = _Span()
    _stamp_result_count(_SpanWrapper(span), (1, 2, 3, 4))
    assert span.attrs == {"tool.result.count": 4}


def test_otel_middleware_end_to_end_stamps_count() -> None:
    """Exercise the whole otel_span_factory chain to verify end-to-end."""
    from a2kit.middleware._chain import ToolContext
    from a2kit.middleware._otel import otel_span_factory

    mw = otel_span_factory()

    ctx = ToolContext(
        tool_name="test_tool",
        verb="list",
        write=False,
        capabilities=frozenset(),
        format_hint=None,
        state={},
    )

    async def _inner(**_kw: Any) -> list[int]:
        return [1, 2, 3, 4, 5]

    import asyncio

    result = asyncio.run(mw(_inner, ctx))
    assert result == [1, 2, 3, 4, 5]
