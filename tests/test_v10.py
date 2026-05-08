"""Tests for v0.10 simplifications:

- Format-from-type at decoration (TSV/TOON locked from return annotation).
- Page[T] with Pydantic models serialises through .model_dump().
- Auto-wired connection_enricher when Router has a store.
- Schema enrichment listing currently-saved connection keys.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, NamedTuple

import pytest
from pydantic import BaseModel

import a2kit
from a2kit import (
    ConnectionInfo,
    ConnectionStore,
    Local,
    Page,
    Passthrough,
    Router,
    connection_enricher,
)
from a2kit.exceptions import ConnectionNotFound
from a2kit.formatter import (
    _dump_items,
    _flat_pydantic_fields,
    format_from_annotation,
    format_response,
)


# ---------------------------------------------------------------- #
# Format-from-type
# ---------------------------------------------------------------- #


class _FlatRow(BaseModel):
    a: int
    b: str
    c: bool | None = None


class _NestedRow(BaseModel):
    a: int
    tags: list[str]


class _AmbiguousRow(BaseModel):
    a: int
    extra: Any = None


def test_flat_pydantic_fields_true_for_scalars() -> None:
    assert _flat_pydantic_fields(_FlatRow) is True


def test_flat_pydantic_fields_false_for_list_field() -> None:
    assert _flat_pydantic_fields(_NestedRow) is False


def test_flat_pydantic_fields_none_for_any_field() -> None:
    assert _flat_pydantic_fields(_AmbiguousRow) is None


def test_format_from_annotation_list_of_flat_pydantic_is_tsv() -> None:
    assert format_from_annotation(list[_FlatRow]) == "tsv"


def test_format_from_annotation_list_of_nested_pydantic_is_toon() -> None:
    assert format_from_annotation(list[_NestedRow]) == "toon"


def test_format_from_annotation_page_of_flat_pydantic_is_tsv() -> None:
    assert format_from_annotation(Page[_FlatRow]) == "tsv"


def test_format_from_annotation_page_of_nested_pydantic_is_toon() -> None:
    assert format_from_annotation(Page[_NestedRow]) == "toon"


def test_format_from_annotation_list_dict_is_none() -> None:
    assert format_from_annotation(list[dict]) is None


def test_format_from_annotation_bare_list_is_none() -> None:
    assert format_from_annotation(list) is None


def test_format_from_annotation_bare_page_is_none() -> None:
    assert format_from_annotation(Page) is None


def test_format_from_annotation_dict_is_json() -> None:
    assert format_from_annotation(dict[str, Any]) == "json"


def test_format_from_annotation_pydantic_single_is_json() -> None:
    assert format_from_annotation(_FlatRow) == "json"


def test_format_from_annotation_scalar_is_json() -> None:
    assert format_from_annotation(int) == "json"
    assert format_from_annotation(str) == "json"


def test_format_from_annotation_none_is_json() -> None:
    assert format_from_annotation(None) == "json"
    assert format_from_annotation(type(None)) == "json"


def test_format_from_annotation_ambiguous_pydantic_is_none() -> None:
    assert format_from_annotation(list[_AmbiguousRow]) is None


def test_format_from_annotation_unknown_falls_back_to_none() -> None:
    assert format_from_annotation(complex) is None


class _OptListRow(BaseModel):
    a: int
    tags: list[str] | None = None  # Optional → still nested


def test_flat_pydantic_fields_optional_list_is_nested() -> None:
    assert _flat_pydantic_fields(_OptListRow) is False


class _NestedModelRow(BaseModel):
    a: int
    inner: _FlatRow


def test_flat_pydantic_fields_nested_basemodel_is_nested() -> None:
    assert _flat_pydantic_fields(_NestedModelRow) is False


def test_format_from_annotation_dict_origin_returns_json() -> None:
    # `dict` (no params) → origin is None; param dict[str, X] → origin is dict.
    from typing import Dict  # noqa: PLC0415, UP035

    assert format_from_annotation(Dict[str, int]) == "json"  # noqa: UP006


def test_format_from_annotation_typing_list_bare_returns_none() -> None:
    # `typing.List` (unparametrised) — get_origin == list, get_args == ().
    from typing import List  # noqa: PLC0415, UP035

    assert format_from_annotation(List) is None  # noqa: UP006


class _MultiUnionRow(BaseModel):
    a: int
    mixed: int | str | None = None  # 3-way union with None — non_none has 2 → skip


def test_flat_pydantic_fields_multi_union_keeps_anno_unchanged() -> None:
    # Multi-non-None union: we don't pick a single anno; field is treated as
    # "flat" (not list/dict/BaseModel), so the row is still flat.
    assert _flat_pydantic_fields(_MultiUnionRow) is True


def test_decorator_handles_unresolvable_forward_ref() -> None:
    # Annotation references a name not in scope. Under `from __future__ import
    # annotations` this is stored as a bare string; `inspect.get_annotations(
    # eval_str=True)` raises NameError. The decorator must fall back to None.
    @a2kit.tool(connection=False)
    def returns_unknown() -> DefinitelyNotAType:  # type: ignore[name-defined]  # noqa: F821
        return {}  # type: ignore[return-value]

    assert returns_unknown._a2kit_format is None  # type: ignore[attr-defined]


# ---------------------------------------------------------------- #
# format_response with hint + Pydantic items
# ---------------------------------------------------------------- #


def test_format_response_honours_tsv_hint_on_list_of_dict() -> None:
    out = format_response([{"a": 1, "b": 2}], format_hint="tsv")
    assert out.format == "tsv"
    assert out.data == "a\tb\n1\t2"


def test_format_response_falls_back_when_hint_incompatible() -> None:
    # hint=tsv but data is a single dict → falls back to JSON.
    out = format_response({"a": 1}, format_hint="tsv")
    assert out.format == "json"


def test_format_response_json_hint_forces_json() -> None:
    out = format_response([{"a": 1}], format_hint="json")
    assert out.format == "json"


def test_format_response_dumps_pydantic_items() -> None:
    rows = [_FlatRow(a=1, b="x"), _FlatRow(a=2, b="y")]
    out = format_response(rows, format_hint="tsv")
    assert out.format == "tsv"
    assert out.data == "a\tb\tc\n1\tx\t\n2\ty\t"


def test_dump_items_skips_non_dict_non_pydantic() -> None:
    out = _dump_items([_FlatRow(a=1, b="x"), {"a": 2, "b": "y"}, "skipped", 42])
    assert out == [{"a": 1, "b": "x", "c": None}, {"a": 2, "b": "y"}]


# ---------------------------------------------------------------- #
# Decorator stamps `_a2kit_format` and uses it at runtime
# ---------------------------------------------------------------- #


def test_decorator_stamps_format_from_return_type() -> None:
    @a2kit.tool(connection=False)
    def list_rows() -> list[_FlatRow]:
        return []

    assert list_rows._a2kit_format == "tsv"  # type: ignore[attr-defined]


def test_decorator_stamps_format_for_dict_return() -> None:
    @a2kit.tool(connection=False)
    def get_thing() -> dict[str, Any]:
        return {}

    assert get_thing._a2kit_format == "json"  # type: ignore[attr-defined]


def test_decorator_stamps_none_when_no_return_annotation() -> None:
    @a2kit.tool(connection=False)
    def untyped():  # type: ignore[no-untyped-def]
        return []

    assert untyped._a2kit_format is None  # type: ignore[attr-defined]


def test_listview_tool_with_pydantic_return_uses_tsv() -> None:
    @a2kit.tool(connection=False, fields=Local)
    def list_rows() -> list[_FlatRow]:
        return [_FlatRow(a=1, b="x"), _FlatRow(a=2, b="y")]

    out = list_rows()
    assert out.format == "tsv"
    assert "a\tb\tc" in out.data


async def test_listview_tool_with_page_pydantic_uses_tsv() -> None:
    @a2kit.tool(connection=False, pagination=Passthrough)
    def list_rows(*, limit: int = 10, cursor: str | None = None) -> Page[_FlatRow]:
        return Page(items=[_FlatRow(a=1, b="x")], next_cursor="abc")

    out = list_rows(limit=10, cursor=None)
    assert out.format == "tsv"
    assert out.next_cursor == "abc"


# ---------------------------------------------------------------- #
# Auto-wired connection_enricher
# ---------------------------------------------------------------- #


class _ConnKey(NamedTuple):
    name: str


class _Conn(ConnectionInfo, key=_ConnKey):
    base_url: str = ""


def _store(tmp_path: Path) -> ConnectionStore[_Conn]:
    """Sync helper — wraps async setup so test bodies stay declarative. Works
    from both sync tests (no loop) and async tests (loop already on this
    thread) by escaping to a fresh worker thread when needed."""
    import anyio  # noqa: PLC0415
    import concurrent.futures  # noqa: PLC0415

    s: ConnectionStore[_Conn] = ConnectionStore(tmp_path, _Conn)

    async def _setup() -> None:
        await s.save(_Conn(key=("prod",), base_url="https://x"))
        await s.save(_Conn(key=("staging",), base_url="https://y"))

    try:
        anyio.run(_setup)
    except RuntimeError:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            ex.submit(anyio.run, _setup).result()
    return s


class WidgetsRouter(Router[_Conn]):
    pass


@WidgetsRouter.read()
def _widgets_list_x(info: _Conn) -> dict:  # type: ignore[type-arg]
    return {"x": info.base_url}


def test_router_auto_enriches_connection_not_found(tmp_path: Path) -> None:
    store = _store(tmp_path)
    server = _FakeServer()
    WidgetsRouter(store=store).register_read(server, store)
    fn = server.tools[-1]

    with pytest.raises(ConnectionNotFound) as exc:
        fn(connection="prdo")  # typo
    msg = str(exc.value)
    assert "Available:" in msg
    assert "prod" in msg
    assert "Did you mean" in msg


def test_router_auto_enricher_can_be_disabled(tmp_path: Path) -> None:
    store = _store(tmp_path)
    server = _FakeServer()
    WidgetsRouter(store=store, auto_connection_enricher=False).register_read(server, store)
    fn = server.tools[-1]

    with pytest.raises(ConnectionNotFound) as exc:
        fn(connection="prdo")
    # Bare ConnectionNotFound — no enrichment.
    assert "Did you mean" not in str(exc.value)


def test_router_explicit_enricher_wins_over_auto(tmp_path: Path) -> None:
    store = _store(tmp_path)
    seen: list[Exception] = []

    def my_enricher(exc: Exception, _name: str | None = None) -> Exception:
        seen.append(exc)
        return RuntimeError("custom")

    server = _FakeServer()
    WidgetsRouter(store=store, enricher=my_enricher).register_read(server, store)
    fn = server.tools[-1]

    with pytest.raises(RuntimeError, match="custom"):
        fn(connection="missing")
    assert len(seen) == 1


# ---------------------------------------------------------------- #
# Schema hint — connection docstring lists saved keys
# ---------------------------------------------------------------- #


def test_connection_param_doc_includes_available_keys(tmp_path: Path) -> None:
    store = _store(tmp_path)
    server = _FakeServer()
    WidgetsRouter(store=store).register_read(server, store)
    fn = server.tools[-1]

    doc = fn.__doc__ or ""
    assert "Currently saved" in doc
    assert "'prod'" in doc
    assert "'staging'" in doc


class GadgetsRouter(Router[_Conn]):
    pass


@GadgetsRouter.read()
def _gadgets_list(info: _Conn) -> dict:  # type: ignore[type-arg]
    return {"ok": 1}


def test_connection_param_doc_falls_back_when_store_has_no_keys(tmp_path: Path) -> None:
    empty_store: ConnectionStore[_Conn] = ConnectionStore(tmp_path, _Conn)
    server = _FakeServer()
    GadgetsRouter(store=empty_store).register_read(server, empty_store)
    fn = server.tools[-1]

    doc = fn.__doc__ or ""
    assert "Currently saved" not in doc
    assert "Saved a2kit connection name" in doc


def test_safe_list_connection_keys_handles_broken_store() -> None:
    from a2kit.tools import _safe_list_connection_keys

    class _Broken:
        def list_connections(self) -> list[Any]:
            raise OSError("disk gone")

    assert _safe_list_connection_keys(_Broken()) is None
    assert _safe_list_connection_keys(None) is None
    assert _safe_list_connection_keys(object()) is None  # no method


# ---------------------------------------------------------------- #
# connection_enricher itself (just to keep coverage tight)
# ---------------------------------------------------------------- #


async def test_connection_enricher_factory_passthrough_for_other_exceptions(tmp_path: Path) -> None:
    enricher = connection_enricher(_store(tmp_path))
    other = ValueError("nope")
    assert await enricher(other) is other


# ---------------------------------------------------------------- #
# Review follow-ups: ephemeral store `list_connections` proxy
# ---------------------------------------------------------------- #


class EphemRouter(Router[_Conn]):
    pass


@EphemRouter.read()
def _ephem_list(info: _Conn) -> dict:  # type: ignore[type-arg]
    return {"x": info.base_url}


def test_ephemeral_store_proxies_list_connections_for_enricher(tmp_path: Path) -> None:
    """Auto-enricher must work on a Router that mixes base + ephemeral connections."""
    base = _store(tmp_path)
    ephemeral: dict[tuple[str, ...], _Conn] = {("ephem-only",): _Conn(key=("ephem-only",), base_url="https://e")}

    server = _FakeServer()
    EphemRouter(store=base, ephemeral=ephemeral).register_read(server, base)
    fn = server.tools[-1]

    with pytest.raises(ConnectionNotFound) as exc:
        fn(connection="missing")
    msg = str(exc.value)
    assert "Available:" in msg
    # Both base and ephemeral keys appear:
    assert "prod" in msg
    assert "ephem-only" in msg


async def test_ephemeral_store_list_connections_dedupes_overrides() -> None:
    """If ephemeral overrides a base key, the ephemeral entry wins (no double-listing)."""
    from a2kit.scaffold import _EphemeralAwareStore

    class _BaseStub:
        async def list_connections(self) -> list[Any]:
            return [_Conn(key=("prod",), base_url="https://base")]

    ephemeral = {("prod",): _Conn(key=("prod",), base_url="https://override")}
    proxy = _EphemeralAwareStore(_BaseStub(), ephemeral)
    keys = [info.key for info in await proxy.list_connections()]
    # Only one "prod" entry survives.
    assert keys.count(("prod",)) == 1


async def test_ephemeral_store_list_connections_with_no_base() -> None:
    """A pure ephemeral router (no base store) still lists ephemeral keys."""
    from a2kit.scaffold import _EphemeralAwareStore

    ephemeral = {("ephem",): _Conn(key=("ephem",), base_url="https://e")}
    proxy = _EphemeralAwareStore(None, ephemeral)
    assert [info.key for info in await proxy.list_connections()] == [("ephem",)]


def test_resolve_return_annotation_propagates_unexpected_errors() -> None:
    """Bug-masking guard: errors outside (NameError, AttributeError, SyntaxError) bubble.

    Otherwise authors get silent `_a2kit_format = None` instead of a stack
    trace pointing at their broken annotation.
    """
    from a2kit.tools import _resolve_return_annotation

    def f() -> int:
        return 0

    f.__annotations__ = {"return": "1/0"}  # eval will raise ZeroDivisionError
    with pytest.raises(ZeroDivisionError):
        _resolve_return_annotation(f, "1/0")


# ---------------------------------------------------------------- #
# Helpers
# ---------------------------------------------------------------- #


class _FakeServer:
    def __init__(self) -> None:
        self.tools: list[Any] = []
        self._tool_manager = self  # mimic shape

    def list_tools(self) -> list[Any]:
        return []

    def tool(self) -> Any:
        def decorator(fn: Any) -> Any:
            self.tools.append(fn)
            return fn

        return decorator
