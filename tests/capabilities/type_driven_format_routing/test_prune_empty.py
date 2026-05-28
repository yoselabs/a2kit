"""A1 — return-type opt-in to empty-field pruning via ``PruneEmpty`` base class."""

from __future__ import annotations

import json
from decimal import Decimal

from pydantic import BaseModel

from a2kit.packages.formatter import PruneEmpty, format_response


class _Pruned(PruneEmpty):
    url: str
    byline: str | None = None
    next_links: list[str] = []
    meta: dict[str, str] = {}
    note: str = ""


class _Plain(BaseModel):
    url: str
    byline: str | None = None
    next_links: list[str] = []
    meta: dict[str, str] = {}
    note: str = ""


class _Zeroish(PruneEmpty):
    count: int = 0
    enabled: bool = False
    price: Decimal = Decimal(0)


class _Inner(PruneEmpty):
    name: str
    note: str | None = None


class _Outer(BaseModel):
    """Non-pruning parent containing a `PruneEmpty` child — cascade test."""

    label: str
    inner: _Inner
    inner_opt: _Inner | None = None


def _structured(value: object) -> object:
    """Return the JSON-decoded structured payload from a ``format_response`` result."""
    resp = format_response(value, format_hint="json")
    return json.loads(resp.data)


def test_base_prunes_none_empty_str_list_dict() -> None:
    pruned = _Pruned(url="https://x", byline=None, next_links=[], meta={}, note="")
    payload = _structured(pruned)
    assert payload == {"url": "https://x"}, f"unexpected: {payload}"


def test_base_preserves_zero_false_decimal_zero() -> None:
    zero = _Zeroish()
    payload = _structured(zero)
    assert payload == {"count": 0, "enabled": False, "price": "0"}, f"unexpected: {payload}"


def test_default_model_emits_all_fields_including_empties() -> None:
    plain = _Plain(url="https://x", byline=None, next_links=[], meta={}, note="")
    payload = _structured(plain)
    assert payload == {
        "url": "https://x",
        "byline": None,
        "next_links": [],
        "meta": {},
        "note": "",
    }, f"unexpected: {payload}"


def test_base_does_not_affect_json_schema() -> None:
    schema_pruned = _Pruned.model_json_schema()
    schema_plain = _Plain.model_json_schema()
    schema_pruned.pop("title", None)
    schema_plain.pop("title", None)
    assert json.dumps(schema_pruned["properties"], sort_keys=True) == json.dumps(schema_plain["properties"], sort_keys=True), (
        "PruneEmpty must not change the JSON schema"
    )
    assert schema_pruned.get("required") == schema_plain.get("required")


def test_cascades_into_nested_prune_empty_child() -> None:
    """Pydantic uses the child's own serializer for nested fields."""
    outer = _Outer(label="L", inner=_Inner(name="n", note=None), inner_opt=None)
    payload = _structured(outer)
    # Outer keeps all its fields (no pruning); inner drops its empty `note`.
    assert payload == {"label": "L", "inner": {"name": "n"}, "inner_opt": None}, f"unexpected: {payload}"
