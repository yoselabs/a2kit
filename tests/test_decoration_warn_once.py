"""WARN-once observability for decoration- and middleware-time introspection
failures (loud-degrade-everywhere change, sites L1-L5).

Each site SHALL emit exactly one WARN-level log line per offender per process
and SHALL proceed with the documented fallback (no return annotation on the
wrapped fn, ``None`` from ``_resolve_return_annotation``, ``()`` from
``_derive_selectable_fields``, unprojected listview payload, empty OTel
metadata).
"""

from __future__ import annotations

import logging
from typing import Any

import pytest

from dataclasses import dataclass

from a2kit import tool as tool_module
from a2kit.packages.di.container import Container


@dataclass
class _DataRow:
    a: int
    b: str


from a2kit.packages.mcp import listview as listview_module
from a2kit.packages.mcp import server as server_module
from a2kit.packages.otel import middleware as otel_middleware_module


@pytest.fixture(autouse=True)
def _reset_warn_once_sets() -> None:
    """Each test starts with empty dedupe sets across all five sites."""
    server_module._WARN_ONCE.clear()
    tool_module._WARN_ONCE_RESOLVE_RETURN.clear()
    tool_module._WARN_ONCE_SELECTABLE.clear()
    listview_module._WARN_ONCE.clear()
    otel_middleware_module._WARN_ONCE.clear()


# ----------------------------------------------------------------------------
# L1 — _wrap_with_dispatch_hook return-annotation copy
# ----------------------------------------------------------------------------


class _Injectable:
    """Marker class used as a typed kwarg to trigger `_has_injectables`."""


def test_l1_dispatch_hook_return_annotation_failure_warns_once(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`_wrap_with_dispatch_hook` swallows annotation-copy failures with one WARN.

    Forces the `get_type_hints` call inside the annotation-copy block to raise
    by monkeypatching `typing.get_type_hints` — directly exercising the
    `except Exception` site without depending on which earlier introspection
    paths inside `wire_input_params` already swallow forward-ref failures.
    """
    container = Container()
    container.register(_Injectable, _Injectable)

    def fn(*, marker: _Injectable):  # type: ignore[no-untyped-def]  # noqa: ANN202 -- no return annotation on purpose
        return None

    def hook(_fn: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
        return kwargs

    import typing as _typing

    real_get_type_hints = _typing.get_type_hints
    calls: list[Any] = []

    def _raising_get_type_hints(target: Any, *args: Any, **kw: Any) -> Any:
        if target is fn:
            calls.append(target)
            raise RuntimeError("forced failure for L1 test")
        return real_get_type_hints(target, *args, **kw)

    monkeypatch.setattr(_typing, "get_type_hints", _raising_get_type_hints)

    with caplog.at_level(logging.WARNING, logger="a2kit.packages.mcp.server"):
        wrapped = server_module._wrap_with_dispatch_hook(fn, hook, container)
        server_module._wrap_with_dispatch_hook(fn, hook, container)

    matches = [r for r in caplog.records if "_wrap_with_dispatch_hook" in r.message]
    assert len(matches) == 1, f"expected 1 WARN, got {len(matches)}: {[r.message for r in matches]}"
    assert "return" not in getattr(wrapped, "__annotations__", {})


# ----------------------------------------------------------------------------
# L2 — _resolve_return_annotation
# ----------------------------------------------------------------------------


def test_l2_resolve_return_annotation_warns_once(caplog: pytest.LogCaptureFixture) -> None:
    """`_resolve_return_annotation` returns None with one WARN on `get_type_hints` failure."""

    def fn() -> "Unresolved":  # type: ignore[name-defined]  # noqa: F821, UP037
        return None  # type: ignore[return-value]

    with caplog.at_level(logging.WARNING, logger="a2kit.tool"):
        out1 = tool_module._resolve_return_annotation(fn)
        out2 = tool_module._resolve_return_annotation(fn)
        out3 = tool_module._resolve_return_annotation(fn)

    assert out1 is None
    assert out2 is None
    assert out3 is None
    matches = [r for r in caplog.records if "_resolve_return_annotation" in r.message]
    assert len(matches) == 1, f"expected 1 WARN, got {len(matches)}"


# ----------------------------------------------------------------------------
# L3 — _derive_selectable_fields outer get_type_hints failure
# ----------------------------------------------------------------------------


def test_l3_derive_selectable_fields_warns_once(caplog: pytest.LogCaptureFixture) -> None:
    """`_derive_selectable_fields` returns () with one WARN on `get_type_hints` failure."""

    def fn() -> "list[Unresolved]":  # type: ignore[name-defined]  # noqa: F821, UP037
        return []

    with caplog.at_level(logging.WARNING, logger="a2kit.tool"):
        out1 = tool_module._derive_selectable_fields(fn)
        out2 = tool_module._derive_selectable_fields(fn)

    assert out1 == ()
    assert out2 == ()
    matches = [r for r in caplog.records if "_derive_selectable_fields" in r.message]
    assert len(matches) == 1, f"expected 1 WARN, got {len(matches)}"


def test_l3_derive_selectable_fields_dataclass_branch_works() -> None:
    """After removing the inner `contextlib.suppress(Exception)`, the dataclass
    branch still resolves fields for a well-formed dataclass.

    `Row` lives at module scope so `get_type_hints` can resolve `list[Row]`
    via the function's `__globals__`.
    """

    def fn() -> list[_DataRow]:
        return []

    assert tool_module._derive_selectable_fields(fn) == ("a", "b")


# ----------------------------------------------------------------------------
# L4 — ListViewMiddleware: get_tool + projection failures
# ----------------------------------------------------------------------------


class _StubParams:
    def __init__(self, name: str) -> None:
        self.name = name


class _StubServer:
    def __init__(self, *, raise_on_get_tool: bool = False, meta: dict[str, Any] | None = None) -> None:
        self._raise = raise_on_get_tool
        self._meta = meta

    async def get_tool(self, _name: str) -> Any:
        if self._raise:
            raise RuntimeError("registry corrupt")

        class _Tool:
            pass

        t = _Tool()
        t.meta = self._meta  # type: ignore[attr-defined]
        return t


class _StubFastMcpCtx:
    def __init__(self, server: Any) -> None:
        self.fastmcp = server
        self.request_id = "req-1"


class _StubMwCtx:
    def __init__(self, *, name: str, fastmcp_context: Any) -> None:
        self.message = _StubParams(name)
        self.fastmcp_context = fastmcp_context


async def _identity_call_next(_ctx: Any) -> Any:
    return "ORIG-RESULT"


async def test_l4_listview_get_tool_failure_warns_once(caplog: pytest.LogCaptureFixture) -> None:
    """`server.get_tool` raises → one WARN per `f'{tool_name}::get_tool'`, result unchanged."""
    mw = listview_module.ListViewMiddleware()
    server = _StubServer(raise_on_get_tool=True)
    ctx = _StubMwCtx(name="broken_tool", fastmcp_context=_StubFastMcpCtx(server))

    with caplog.at_level(logging.WARNING, logger="a2kit.packages.mcp.listview"):
        out1 = await mw.on_call_tool(ctx, _identity_call_next)
        out2 = await mw.on_call_tool(ctx, _identity_call_next)

    assert out1 == "ORIG-RESULT"
    assert out2 == "ORIG-RESULT"
    matches = [r for r in caplog.records if "server.get_tool failed" in r.message]
    assert len(matches) == 1
    assert "broken_tool::get_tool" in listview_module._WARN_ONCE


class _RejectingResult:
    """Result whose `type(self)(...)` constructor rejects kwargs.

    First construction (the seed) is allowed via the ``_seed`` keyword so we
    can hand the middleware a pre-populated instance; any subsequent
    construction (the reconstruction attempt inside the middleware) raises.
    """

    def __init__(self, *, _seed: bool = False, **_kwargs: Any) -> None:
        if not _seed:
            raise RuntimeError("cannot reconstruct")
        self.content: list[Any] = []
        self.structured_content: dict[str, Any] = {"result": [{"a": 1, "b": 2}]}
        self.meta: Any = None


async def test_l4_listview_projection_failure_warns_once(caplog: pytest.LogCaptureFixture) -> None:
    """Result reconstruction raises → one WARN per `f'{tool_name}::project'`, original result returned."""
    mw = listview_module.ListViewMiddleware()
    server = _StubServer(meta={"a2kit": {"extras": {"list_view": {"default_fields": ["a"]}}}})
    ctx = _StubMwCtx(name="proj_tool", fastmcp_context=_StubFastMcpCtx(server))

    seed = _RejectingResult(_seed=True)

    async def _seed_call_next(_ctx: Any) -> Any:
        return seed

    with caplog.at_level(logging.WARNING, logger="a2kit.packages.mcp.listview"):
        out1 = await mw.on_call_tool(ctx, _seed_call_next)
        out2 = await mw.on_call_tool(ctx, _seed_call_next)

    assert out1 is seed
    assert out2 is seed
    matches = [r for r in caplog.records if "result reconstruction failed" in r.message]
    assert len(matches) == 1
    assert "proj_tool::project" in listview_module._WARN_ONCE


# ----------------------------------------------------------------------------
# L5 — OTel middleware metadata lookup failure
# ----------------------------------------------------------------------------


async def test_l5_otel_meta_lookup_failure_warns_once(caplog: pytest.LogCaptureFixture) -> None:
    """`server.get_tool` raises in `_meta_a2kit` → one WARN per `tool_name`, empty meta."""
    server = _StubServer(raise_on_get_tool=True)
    fastmcp_ctx = _StubFastMcpCtx(server)

    with caplog.at_level(logging.WARNING, logger="a2kit.packages.otel.middleware"):
        out1 = await otel_middleware_module._meta_a2kit(fastmcp_ctx, "broken_tool")
        out2 = await otel_middleware_module._meta_a2kit(fastmcp_ctx, "broken_tool")
        out3 = await otel_middleware_module._meta_a2kit(fastmcp_ctx, "other_broken")

    assert out1 == {}
    assert out2 == {}
    assert out3 == {}
    matches = [r for r in caplog.records if "_meta_a2kit" in r.message]
    assert len(matches) == 2, f"expected 2 WARNs (one per tool_name), got {len(matches)}"
    assert "broken_tool" in otel_middleware_module._WARN_ONCE
    assert "other_broken" in otel_middleware_module._WARN_ONCE
