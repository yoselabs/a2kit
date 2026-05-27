"""Mirror tests for `packages/http/_error_render_stage` — HTTP error-render stage."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.responses import JSONResponse

from a2effect import AppError
from a2effect.errors import AuthError, InfrastructureError, InputError, PolicyError
from a2kit.packages.dispatch import CapturedError, get_rendered_error  # noqa: F401 -- imported for parity demonstration
from a2kit.packages.dispatch._render_state import RenderedError, set_rendered_error
from a2kit.packages.http._error_render_stage import HttpErrorRenderStage, http_status_for


# ---------- http_status_for: pure mapping ---------- #


class _NotFound(AppError):
    kind = "input"
    http_status = 404


class _Custom(AppError):
    kind = "input"
    http_status = 418


def test_http_status_class_override_wins():
    assert http_status_for(_NotFound("x")) == 404
    assert http_status_for(_Custom("x")) == 418


def test_http_status_kind_map_fallback():
    assert http_status_for(InputError("x")) == 400
    assert http_status_for(AuthError("x")) == 401
    assert http_status_for(PolicyError("x")) == 403
    assert http_status_for(InfrastructureError("x")) == 503


# Unknown-kind 500 fallthrough is defensive-only; a2effect's `__init_subclass__`
# rejects unknown kinds at class definition time, so the path is dead code by
# construction. Kept in source as belt-and-suspenders against future a2effect
# changes that relax the kind allowlist.


# ---------- HttpErrorRenderStage: catches CapturedError, reads side-channel ---------- #


async def _invoke_stage_with(exc: AppError, *, populate_side_channel: bool) -> Any:
    """Invoke the stage's wrapped fn. The stage itself opens render_state internally.

    For the populated path, the inner ``fn`` (simulating ``ErrorEnvelopeStage``)
    publishes a ``RenderedError`` before raising. For the empty path, the
    inner ``fn`` just raises without publishing — exercises the defensive
    fallback.
    """

    async def _raiser() -> None:
        if populate_side_channel:
            set_rendered_error(exc, RenderedError(prose="prose", envelope={"type": type(exc).__name__, "kind": exc.kind}))
        raise CapturedError(exc) from exc

    stage = HttpErrorRenderStage()
    wrapped = stage.wrap(_raiser, spec=None)
    return await wrapped()


async def test_stage_returns_jsonresponse_on_apperror_with_side_channel():
    exc = _NotFound("missing")
    result = await _invoke_stage_with(exc, populate_side_channel=True)
    assert isinstance(result, JSONResponse)
    assert result.status_code == 404
    # Body bytes carry {"error": <envelope>}
    body = result.body.decode("utf-8")
    assert '"error"' in body
    assert '"type":"_NotFound"' in body or '"type": "_NotFound"' in body


async def test_stage_status_comes_from_class_override():
    exc = _Custom("teapot")
    result = await _invoke_stage_with(exc, populate_side_channel=True)
    assert isinstance(result, JSONResponse)
    assert result.status_code == 418


async def test_stage_status_falls_through_kind_map_when_no_override():
    exc = InfrastructureError("down")
    result = await _invoke_stage_with(exc, populate_side_channel=True)
    assert isinstance(result, JSONResponse)
    assert result.status_code == 503


async def test_stage_reraises_when_side_channel_empty_defensive():
    """Defensive fallback path: no RenderedError published → re-raise so substrate handler covers."""
    exc = InputError("x")
    with pytest.raises(InputError):
        await _invoke_stage_with(exc, populate_side_channel=False)


async def test_stage_reraises_non_apperror_captured():
    """Non-AppError CapturedError → re-raise the original (substrate quarantines)."""
    inner = KeyError("oops")

    async def _raiser() -> None:
        raise CapturedError(inner) from inner

    stage = HttpErrorRenderStage()
    wrapped = stage.wrap(_raiser, spec=None)
    with pytest.raises(KeyError):
        await wrapped()


async def test_stage_does_not_swallow_unrelated_exceptions():
    """Non-CapturedError exceptions propagate untouched."""

    async def _raiser() -> None:
        raise RuntimeError("not captured")

    stage = HttpErrorRenderStage()
    wrapped = stage.wrap(_raiser, spec=None)
    with pytest.raises(RuntimeError, match="not captured"):
        await wrapped()
