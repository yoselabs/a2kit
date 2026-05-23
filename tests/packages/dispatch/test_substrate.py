"""Unit tests for :mod:`a2kit.packages.dispatch.substrate`.

Covers the three-way classification (substrate-reserved / Container-known
/ wire) for both ``fastapi`` and ``fastmcp`` substrates, plus annotation
unwrapping (``Annotated``, ``Optional``, ``T | None``) and the
cross-substrate misclassification error path.

FastAPI-dependent tests are skipped until task 2.6 adds the dep. The
Starlette half of the FastAPI allowlist (``Request``/``Response``/
``WebSocket``) is available transitively via ``fastmcp`` and is
exercised here directly.
"""

from __future__ import annotations

from typing import Annotated, Union

import fastmcp
import pytest
from starlette.requests import Request

from a2kit.packages.di.container import Container
from a2kit.packages.dispatch.substrate import (
    SplitSignature,
    SubstrateSignatureError,
    _FASTAPI_RESERVED_SPECS,
    _FASTMCP_RESERVED_SPECS,
    _force_reserved,
    fastapi_reserved,
    fastmcp_reserved,
    split_signature,
)


class _Database:
    """Stand-in for a DI-provided dependency."""


class _Body:
    """Stand-in for a wire-side pydantic-shaped type with no provider."""


def _container_with_db() -> Container:
    c = Container()
    c.provide(_Database)
    return c


# ---------------------------------------------------------------------------
# Wire / Container-known split (no substrate-reserved types involved)
# ---------------------------------------------------------------------------


def test_wire_and_container_split_on_fastapi() -> None:
    async def fn(*, id: str, db: _Database) -> str:  # noqa: ARG001
        return id

    split = split_signature(fn, "fastapi", _container_with_db())
    assert split.substrate == "fastapi"
    assert set(split.wire) == {"id"}
    assert set(split.container) == {"db"}
    assert set(split.reserved) == set()


def test_wire_and_container_split_on_fastmcp() -> None:
    async def fn(*, id: str, db: _Database) -> str:  # noqa: ARG001
        return id

    split = split_signature(fn, "fastmcp", _container_with_db())
    assert set(split.wire) == {"id"}
    assert set(split.container) == {"db"}
    assert set(split.reserved) == set()


def test_body_without_provider_is_wire() -> None:
    """A type a2kit DI doesn't know about goes to wire — substrate decodes it."""

    async def fn(*, body: _Body) -> str:  # noqa: ARG001
        return "ok"

    split = split_signature(fn, "fastapi", Container())
    assert set(split.wire) == {"body"}
    assert set(split.container) == set()


# ---------------------------------------------------------------------------
# Annotation unwrapping
# ---------------------------------------------------------------------------


def test_annotated_metadata_is_stripped() -> None:
    async def fn(*, db: Annotated[_Database, "marker"], id: str) -> str:  # noqa: ARG001
        return id

    split = split_signature(fn, "fastmcp", _container_with_db())
    assert set(split.container) == {"db"}
    assert set(split.wire) == {"id"}


def test_optional_type_unwraps_to_inner() -> None:
    async def fn(*, db: _Database | None = None, id: str = "x") -> str:  # noqa: ARG001, UP007
        return id

    split = split_signature(fn, "fastmcp", _container_with_db())
    assert set(split.container) == {"db"}
    assert set(split.wire) == {"id"}


def test_pep604_union_with_none_unwraps() -> None:
    async def fn(*, db: _Database | None = None, id: str = "x") -> str:  # noqa: ARG001
        return id

    split = split_signature(fn, "fastmcp", _container_with_db())
    assert set(split.container) == {"db"}
    assert set(split.wire) == {"id"}


def test_typing_union_with_none_unwraps() -> None:
    async def fn(*, db: Union[_Database, None] = None, id: str = "x") -> str:  # noqa: ARG001, UP007
        return id

    split = split_signature(fn, "fastmcp", _container_with_db())
    assert set(split.container) == {"db"}
    assert set(split.wire) == {"id"}


def test_multi_arm_union_without_none_stays_wire() -> None:
    """``str | int`` has no clean inner type; the substrate decides decoding."""

    async def fn(*, value: str | int) -> str:  # noqa: ARG001
        return "ok"

    split = split_signature(fn, "fastapi", Container())
    assert set(split.wire) == {"value"}
    assert set(split.container) == set()


# ---------------------------------------------------------------------------
# Substrate-reserved bucket — Starlette types (available via fastmcp)
# ---------------------------------------------------------------------------


def test_fastapi_request_is_reserved() -> None:
    """``Request`` from Starlette is FastAPI-reserved; passes through."""

    async def fn(*, request: Request, id: str, db: _Database) -> str:  # noqa: ARG001
        return id

    split = split_signature(fn, "fastapi", _container_with_db())
    assert set(split.reserved) == {"request"}
    assert set(split.wire) == {"id"}
    assert set(split.container) == {"db"}


def test_fastapi_background_tasks_is_reserved() -> None:
    """BackgroundTasks lives in fastapi; skipped until 2.6 lands the dep."""
    fastapi = pytest.importorskip("fastapi")

    async def fn(*, tasks: fastapi.BackgroundTasks, id: str) -> str:  # noqa: ARG001
        return id

    split = split_signature(fn, "fastapi", Container())
    assert set(split.reserved) == {"tasks"}
    assert set(split.wire) == {"id"}


def test_fastmcp_context_is_reserved() -> None:
    async def fn(*, ctx: fastmcp.Context, id: str, db: _Database) -> str:  # noqa: ARG001
        return id

    split = split_signature(fn, "fastmcp", _container_with_db())
    assert set(split.reserved) == {"ctx"}
    assert set(split.wire) == {"id"}
    assert set(split.container) == {"db"}


# ---------------------------------------------------------------------------
# Cross-substrate misclassification
# ---------------------------------------------------------------------------


def test_context_on_fastapi_raises() -> None:
    """``ctx: Context`` belongs to fastmcp; raise when registered on fastapi."""

    async def fn(*, ctx: fastmcp.Context, id: str) -> str:  # noqa: ARG001
        return id

    with pytest.raises(SubstrateSignatureError) as ei:
        split_signature(fn, "fastapi", Container())
    err = ei.value
    assert err.param_name == "ctx"
    assert err.wrong_substrate == "fastapi"
    assert err.right_substrate == "fastmcp"
    assert "Context" in str(err)


def test_request_on_fastmcp_raises() -> None:
    """``Request`` belongs to fastapi; raise when registered on fastmcp."""

    async def fn(*, request: Request, id: str) -> str:  # noqa: ARG001
        return id

    with pytest.raises(SubstrateSignatureError) as ei:
        split_signature(fn, "fastmcp", Container())
    err = ei.value
    assert err.param_name == "request"
    assert err.wrong_substrate == "fastmcp"
    assert err.right_substrate == "fastapi"


# ---------------------------------------------------------------------------
# Substrate-reserved beats Container-known precedence
# ---------------------------------------------------------------------------


def test_reserved_beats_container_when_both_match() -> None:
    """If an author registers a provider for a substrate-reserved type, the
    substrate-reserved classification wins — the substrate populates it,
    DI does not.
    """
    c = Container()
    c.provide(Request, lambda: None)  # pathological: provider for reserved type

    async def fn(*, request: Request) -> str:  # noqa: ARG001
        return "ok"

    split = split_signature(fn, "fastapi", c)
    assert set(split.reserved) == {"request"}
    assert set(split.container) == set()


# ---------------------------------------------------------------------------
# Allowlist membership baseline (1.7 — full inventory once deps installed)
# ---------------------------------------------------------------------------


def test_fastapi_reserved_baseline() -> None:
    """Force-imports every FastAPI allowlist module; asserts exact membership.

    Skipped until task 2.6 adds the ``fastapi`` dependency.
    """
    fastapi = pytest.importorskip("fastapi")
    from starlette.responses import Response
    from starlette.websockets import WebSocket

    materialized = _force_reserved(_FASTAPI_RESERVED_SPECS)
    assert materialized == frozenset({Request, Response, fastapi.BackgroundTasks, WebSocket})


def test_fastmcp_reserved_baseline() -> None:
    """Force-imports the FastMCP allowlist module; asserts exact membership."""
    materialized = _force_reserved(_FASTMCP_RESERVED_SPECS)
    assert materialized == frozenset({fastmcp.Context})


def test_lazy_accessors_match_force_when_loaded() -> None:
    """Once substrate modules are imported, the lazy accessor returns the same set."""
    assert fastmcp_reserved() == _force_reserved(_FASTMCP_RESERVED_SPECS)
    # FastAPI half: only assert the lazy accessor matches the force-loaded set
    # when fastapi is importable in the test environment.
    if pytest.importorskip.__name__:  # always true; sentinel for the dual case
        try:
            import fastapi  # noqa: F401
        except ImportError:
            return
        assert fastapi_reserved() == _force_reserved(_FASTAPI_RESERVED_SPECS)


# ---------------------------------------------------------------------------
# Dataclass shape
# ---------------------------------------------------------------------------


def test_splitsignature_is_frozen() -> None:
    split = SplitSignature(substrate="fastapi")
    with pytest.raises(Exception):  # noqa: B017, PT011 -- FrozenInstanceError or AttributeError
        split.substrate = "fastmcp"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# install_substrate_signature — wrapper emission
# ---------------------------------------------------------------------------


import inspect as _inspect  # noqa: E402

from a2kit.packages.dispatch.substrate import (  # noqa: E402
    _a2kit_scope,
    install_substrate_signature,
)


class _DBService:
    def __init__(self) -> None:
        self.calls: list[str] = []


@pytest.mark.asyncio
async def test_wrapper_signature_lists_only_reserved_and_wire() -> None:
    """``__signature__`` exposes substrate-routed params only — DI is hidden."""

    async def fn(*, id: str, db: _DBService) -> str:  # noqa: ARG001
        return id

    c = Container()
    c.provide(_DBService)
    async with c:
        wrapper = install_substrate_signature(fn, "fastmcp", c)

    sig = _inspect.signature(wrapper)
    assert set(sig.parameters) == {"id"}
    assert sig.return_annotation is str


@pytest.mark.asyncio
async def test_wrapper_resolves_di_and_passes_wire() -> None:
    """DI is resolved inside the wrapper; wire kwargs pass through."""

    async def fn(*, id: str, db: _DBService) -> str:
        db.calls.append(id)
        return f"got:{id}"

    c = Container()
    db = _DBService()
    c.provide(_DBService, lambda: db)
    async with c:
        wrapper = install_substrate_signature(fn, "fastmcp", c)
        result = await wrapper(id="x")
    assert result == "got:x"
    assert db.calls == ["x"]


@pytest.mark.asyncio
async def test_wrapper_merges_reserved_kwargs() -> None:
    """Reserved kwargs the substrate populated land on fn alongside wire+DI."""

    async def fn(*, ctx: fastmcp.Context, id: str, db: _DBService) -> str:  # noqa: ARG001
        return f"{id}:{type(ctx).__name__}"

    c = Container()
    c.provide(_DBService)
    async with c:
        wrapper = install_substrate_signature(fn, "fastmcp", c)
        fake_ctx = type("FakeCtx", (), {})()
        result = await wrapper(id="abc", ctx=fake_ctx)
    assert result == "abc:FakeCtx"


@pytest.mark.asyncio
async def test_wrapper_sets_scope_contextvar() -> None:
    """``_a2kit_scope`` is set inside the wrapper body and reset on exit."""
    observed: dict[str, object | None] = {"during": None, "after": None}

    async def fn(*, id: str) -> str:
        observed["during"] = _a2kit_scope.get()
        return id

    c = Container()
    async with c:
        wrapper = install_substrate_signature(fn, "fastmcp", c)
        await wrapper(id="x")
        observed["after"] = _a2kit_scope.get()

    assert observed["during"] is not None
    assert observed["after"] is None


@pytest.mark.asyncio
async def test_wrapper_resets_scope_on_exception() -> None:
    """The scope token is reset even when ``fn`` raises."""

    class _Boom(Exception):
        pass

    async def fn(*, id: str) -> str:  # noqa: ARG001
        raise _Boom

    c = Container()
    async with c:
        wrapper = install_substrate_signature(fn, "fastmcp", c)
        with pytest.raises(_Boom):
            await wrapper(id="x")
        assert _a2kit_scope.get() is None


@pytest.mark.asyncio
async def test_wrapper_works_with_sync_fn() -> None:
    """``fn`` may be sync; wrapper awaits the result via ``isawaitable`` check."""

    def fn(*, id: str) -> str:
        return f"sync:{id}"

    c = Container()
    async with c:
        wrapper = install_substrate_signature(fn, "fastmcp", c)
        result = await wrapper(id="y")
    assert result == "sync:y"


@pytest.mark.asyncio
async def test_wrapper_signature_includes_reserved() -> None:
    """``Context`` appears in the wrapper signature (substrate routes it)."""

    async def fn(*, ctx: fastmcp.Context, id: str, db: _DBService) -> str:  # noqa: ARG001
        return id

    c = Container()
    c.provide(_DBService)
    async with c:
        wrapper = install_substrate_signature(fn, "fastmcp", c)

    sig = _inspect.signature(wrapper)
    assert set(sig.parameters) == {"ctx", "id"}
    # PEP 563 stringified annotations: param.annotation is the raw string;
    # resolved hints live on the wrapper's __annotations__ post-rewrite.
    assert wrapper.__annotations__["ctx"] is fastmcp.Context
