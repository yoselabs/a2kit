"""Tests for v0.8 polish bundle: projection=True, ephemeral lift, Response model."""

from __future__ import annotations

import inspect
from typing import Any

import pytest
from pydantic import ValidationError

import a2kit
from a2kit._context import _RouterContext


def _ctx(name: str = "test") -> _RouterContext[Any]:
    return _RouterContext(router_name=name, fqn=f"tests.{name}")


# ---- projection=True --------------------------------------------------------


def test_projection_injects_filter_fields_into_signature() -> None:
    rows = [{"a": 1}, {"a": 5}]

    @a2kit.tool(projection=True)
    def list_widgets() -> list[dict]:
        """Return widgets."""
        return rows

    sig = inspect.signature(list_widgets)
    assert "filter" in sig.parameters
    assert "fields" in sig.parameters
    assert sig.parameters["filter"].default == ""
    assert sig.parameters["fields"].default is None


def test_projection_filters_via_synthetic_param() -> None:
    rows = [{"a": 1}, {"a": 5}]

    @a2kit.tool(projection=True)
    def list_widgets() -> list[dict]:
        return rows

    out = list_widgets(filter="a > 3")  # type: ignore[call-arg]
    assert isinstance(out, a2kit.Response)
    assert out.format == "toon"
    assert "5" in out.data


def test_projection_fields_via_synthetic_param() -> None:
    rows = [{"a": 1, "b": 2}]

    @a2kit.tool(projection=True)
    def list_widgets() -> list[dict]:
        return rows

    out = list_widgets(fields=["a"])  # type: ignore[call-arg]
    assert "b" not in out.data


def test_projection_no_args_passthrough() -> None:
    rows = [{"a": 1}]

    @a2kit.tool(projection=True)
    def list_widgets() -> list[dict]:
        return rows

    out = list_widgets()
    assert out == rows


async def test_projection_async() -> None:
    rows = [{"v": 10}, {"v": 1}]

    @a2kit.tool(projection=True)
    async def list_widgets() -> list[dict]:
        return rows

    out = await list_widgets(filter="v > 5")  # type: ignore[call-arg]
    assert isinstance(out, a2kit.Response)
    assert "10" in out.data


def test_projection_combined_with_explicit_kwargs_rejected() -> None:
    with pytest.raises(ValueError, match="projection=True"):

        @a2kit.tool(projection=True, cel_filter_param="filter")
        def f() -> list[dict]:
            return []


def test_projection_collision_with_existing_filter_param_rejected() -> None:
    with pytest.raises(ValueError, match="filter` or `fields`"):

        @a2kit.tool(projection=True)
        def f(filter: str = "") -> list[dict]:  # noqa: A002
            return []


def test_projection_collision_with_existing_fields_param_rejected() -> None:
    with pytest.raises(ValueError, match="filter` or `fields`"):

        @a2kit.tool(projection=True)
        def f(fields: list[str] | None = None) -> list[dict]:
            return []


def test_projection_non_str_filter_silently_ignored() -> None:
    rows = [{"a": 1}]

    @a2kit.tool(projection=True)
    def list_widgets() -> list[dict]:
        return rows

    out = list_widgets(filter=123)  # type: ignore[call-arg]
    assert out == rows


def test_projection_non_list_fields_silently_ignored() -> None:
    rows = [{"a": 1}]

    @a2kit.tool(projection=True)
    def list_widgets() -> list[dict]:
        return rows

    out = list_widgets(fields="nope")  # type: ignore[call-arg]
    assert out == rows


def test_projection_signature_inserts_before_var_keyword() -> None:
    @a2kit.tool(projection=True)
    def f(**extra: Any) -> list[dict]:
        return []

    sig = inspect.signature(f)
    params = list(sig.parameters.values())
    # filter, fields go BEFORE the **extra terminator.
    assert params[-1].kind == inspect.Parameter.VAR_KEYWORD
    kinds = [p.kind for p in params[:-1]]
    assert inspect.Parameter.KEYWORD_ONLY in kinds


# ---- ephemeral lift ---------------------------------------------------------


def test_ephemeral_aware_store_short_circuits() -> None:
    from a2kit.scaffold import _EphemeralAwareStore

    class _Conn(a2kit.ConnectionInfo):
        url: str

    eph = {("eph",): _Conn(key=("eph",), url="https://eph")}
    proxy = _EphemeralAwareStore(None, eph)
    assert proxy.load(("eph",)).url == "https://eph"


def test_ephemeral_aware_store_falls_through_to_base() -> None:
    from a2kit.scaffold import _EphemeralAwareStore
    from a2kit.exceptions import ConnectionNotFound

    proxy = _EphemeralAwareStore(None, {})
    with pytest.raises(ConnectionNotFound):
        proxy.load(("missing",))


# ---- Response model ---------------------------------------------------------


def test_response_model_frozen() -> None:
    r = a2kit.format_response([{"a": 1}])
    with pytest.raises(ValidationError):
        r.format = "json"  # type: ignore[misc]


def test_response_next_cursor_default_none() -> None:
    r = a2kit.format_response([{"a": 1}])
    assert r.next_cursor is None
