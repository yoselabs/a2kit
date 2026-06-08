"""The six dispatch stages — self-skip rule and active behaviour.

Each stage is driven directly: construct the stage, call ``wrap`` with a
stub ``fn`` and a ``ToolBuildSpec``, no MCP server or CLI command built.
"""

from __future__ import annotations

import asyncio
from typing import Any

import anyio
import pytest

import a2kit
from a2kit.runtime import build
from a2kit.metadata import _get_meta
from a2kit.packages.dispatch import (
    CapturedError,
    DispatchHookStage,
    EnricherStage,
    ErrorCaptureStage,
    CallScopeStage,
    RouterLazyEnterStage,
    TimeoutStage,
    ToolBuildSpec,
)


def _spec(app: a2kit.App, router: Any = None, meta: Any = None) -> ToolBuildSpec:
    return ToolBuildSpec(app=build(app), router=router, meta=meta)


async def _stub() -> dict:
    return {"ok": True}


# --- TimeoutStage -------------------------------------------------------- #


def test_timeout_stage_self_skips_when_unconfigured() -> None:
    stage = TimeoutStage()
    spec = _spec(a2kit.App("t"))
    assert stage.wrap(_stub, spec) is _stub


def test_timeout_stage_fires_when_configured() -> None:
    class _Slow(a2kit.Router):
        slug = "slow"

        @a2kit.read(timeout=0.05)
        async def crawl(self) -> dict:
            await anyio.sleep(2)
            return {}

    app = a2kit.App("timeout-app")
    app.add_router(_Slow())
    desc = app.tools()[0]
    spec = _spec(app, router=app.router_instances()[0], meta=_get_meta(desc.fn))
    wrapped = TimeoutStage().wrap(desc.fn, spec)
    assert wrapped is not desc.fn
    with pytest.raises(TimeoutError):
        asyncio.run(wrapped())


# --- EnricherStage ------------------------------------------------------- #


def test_enricher_stage_quarantines_uncaught_raises_without_enrichers() -> None:
    """With the typed-error contract every raise becomes either an
    enricher-translated AppError or an UnexpectedDefect; ValueError no
    longer leaks through bare."""
    from a2effect import UnexpectedDefect

    class _Plain(a2kit.Router):
        slug = "plain-q"

        @a2kit.read()
        async def boom(self) -> dict:
            raise ValueError("orig")

    app = a2kit.App("plain-q-app")
    app.add_router(_Plain())
    desc = app.tools()[0]
    spec = _spec(app, router=app.router_instances()[0], meta=_get_meta(desc.fn))
    wrapped = EnricherStage().wrap(desc.fn, spec)
    with pytest.raises(UnexpectedDefect):
        asyncio.run(wrapped())


def test_enricher_stage_translates_exceptions_via_decorator() -> None:
    from a2effect import AppError

    class Translated(AppError):
        kind = "infra"

    class _Enriched(a2kit.Router):
        slug = "enriched"

        @a2kit.read()
        async def boom(self) -> dict:
            raise ValueError("orig")

    router = _Enriched()

    @router.enricher
    def translate(exc: ValueError) -> Translated | None:
        return Translated(f"enriched: {exc}")

    app = a2kit.App("enricher-app").add_router(router)
    desc = app.tools()[0]
    spec = _spec(app, router=app.router_instances()[0], meta=_get_meta(desc.fn))
    wrapped = EnricherStage().wrap(desc.fn, spec)
    with pytest.raises(Translated, match="enriched: orig"):
        asyncio.run(wrapped())


# --- RouterLazyEnterStage ----------------------------------------------- #


def test_router_lazy_enter_self_skips_without_aenter() -> None:
    class _Plain(a2kit.Router):
        slug = "plain2"

        @a2kit.read()
        async def ping(self) -> dict:
            return {"ok": True}

    app = a2kit.App("plain2-app")
    app.add_router(_Plain())
    desc = app.tools()[0]
    spec = _spec(app, router=app.router_instances()[0], meta=_get_meta(desc.fn))
    assert RouterLazyEnterStage().wrap(desc.fn, spec) is desc.fn


def test_router_lazy_enter_enters_router_on_dispatch() -> None:
    class _Lifecycle(a2kit.Router):
        slug = "lifecycle"

        def __init__(self) -> None:
            super().__init__()
            self.entered = False

        async def __aenter__(self) -> _Lifecycle:
            self.entered = True
            return self

        async def __aexit__(self, *exc: object) -> None:
            return None

        @a2kit.read()
        async def ping(self) -> dict:
            return {"ok": True}

    app = a2kit.App("lifecycle-app")
    router = _Lifecycle()
    app.add_router(router)
    desc = app.tools()[0]
    spec = _spec(app, router=app.router_instances()[0], meta=_get_meta(desc.fn))
    wrapped = RouterLazyEnterStage().wrap(desc.fn, spec)
    assert wrapped is not desc.fn
    asyncio.run(wrapped())
    assert router.entered is True
    assert "lifecycle" in spec.app._entered_routers  # noqa: SLF001 -- runtime lifecycle seam


# --- DispatchHookStage --------------------------------------------------- #


def test_dispatch_hook_self_skips_on_identity_hook_with_no_injectables() -> None:
    stage = DispatchHookStage()
    assert stage.wrap(_stub, _spec(a2kit.App("t"))) is _stub


# --- CallScopeStage ------------------------------------------------------ #


def test_call_scope_stage_never_self_skips_and_runs_the_body() -> None:
    stage = CallScopeStage()
    wrapped = stage.wrap(_stub, _spec(a2kit.App("t")))
    assert wrapped is not _stub
    assert asyncio.run(wrapped()) == {"ok": True}


# --- ErrorCaptureStage --------------------------------------------------- #


def test_error_capture_wraps_a_body_exception() -> None:
    async def _boom() -> dict:
        raise ValueError("kaboom")

    wrapped = ErrorCaptureStage().wrap(_boom, _spec(a2kit.App("t")))
    with pytest.raises(CapturedError) as excinfo:
        asyncio.run(wrapped())
    assert isinstance(excinfo.value.original, ValueError)
    assert excinfo.value.message == "kaboom"


def test_error_capture_passes_a_normal_return_through() -> None:
    wrapped = ErrorCaptureStage().wrap(_stub, _spec(a2kit.App("t")))
    assert asyncio.run(wrapped()) == {"ok": True}


def test_error_capture_reraises_pure_cancellation_groups() -> None:
    async def _cancelled() -> dict:
        raise BaseExceptionGroup("cancelled", [asyncio.CancelledError()])

    wrapped = ErrorCaptureStage().wrap(_cancelled, _spec(a2kit.App("t")))
    with pytest.raises(BaseExceptionGroup):
        asyncio.run(wrapped())
