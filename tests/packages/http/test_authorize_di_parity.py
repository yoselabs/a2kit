"""Authorize-gate DI parity between HTTP and MCP — regression net for `dispatch-pipeline-parity-on-http`.

Today both transports route through `_run_authorize_gate(authorize, container)`,
which opens its own `call_scope` and resolves the callable's deps. The
refactor moves HTTP onto the shared pipeline; this test pins the contract
that an `authorize=` callable resolving a Container-known dependency MUST
allow and deny identically on both transports.

If this ever drifts, S13 has regressed and the wire shape is at risk.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi.testclient import TestClient

import a2kit
from a2effect import AppError, Raises
from a2kit.packages.http.build import build_http_app
from a2kit.runtime import build


# A Container-resolved dependency the authorize callable consumes.
@dataclass
class _AccessPolicy:
    allow: bool


def _authz_via_di(*, policy: _AccessPolicy) -> bool:
    """Authorize gate that pulls `policy` from the Container.

    On both transports this MUST resolve through `Container.call_scope` and
    return the policy's `allow` flag. The tool body MUST NOT be invoked when
    the gate returns False.
    """
    return policy.allow


class _Denied(AppError):
    kind = "policy"
    http_status = 403


def _build_runtime(*, allow: bool):
    body_calls: list[int] = []
    app = a2kit.App("authz-di-parity").provide(_AccessPolicy, lambda: _AccessPolicy(allow=allow))

    class R(a2kit.Router):
        slug = "svc"

        @a2kit.read(authorize=_authz_via_di)
        async def call(self, *, x: int) -> Annotated[dict, Raises(_Denied)]:
            body_calls.append(x)
            return {"x": x}

    app.add_router(R())
    return build(app), body_calls


# ---------- HTTP path ---------- #


def test_http_authorize_with_di_allows_when_policy_allows() -> None:
    runtime, body_calls = _build_runtime(allow=True)
    client = TestClient(build_http_app(runtime), raise_server_exceptions=False)
    resp = client.post("/call", json={"x": 7})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"x": 7}
    assert body_calls == [7]


def test_http_authorize_with_di_denies_when_policy_denies() -> None:
    runtime, body_calls = _build_runtime(allow=False)
    client = TestClient(build_http_app(runtime), raise_server_exceptions=False)
    resp = client.post("/call", json={"x": 9})
    assert resp.status_code == 403, resp.text
    body = resp.json()
    assert body["error"]["type"] == "AuthorizationDenied"
    assert body_calls == [], "tool body MUST NOT run when authorize denied"


# ---------- MCP path (via direct dispatch fold, not a full FastMCP server) ---------- #


async def test_mcp_authorize_with_di_allows_when_policy_allows() -> None:
    """Exercise the same tool through the dispatch pipeline as MCP folds it.

    Mirrors `mcp/server.py::_build_one_tool` semantics: take the descriptor's
    `fn`, fold `DISPATCH_PIPELINE` around it, invoke. The authorize-gate
    stage in the pipeline resolves the `_AccessPolicy` dependency from the
    Container and returns True; the body runs.
    """
    from a2kit.packages.dispatch import DISPATCH_PIPELINE, fold_pipeline
    from a2kit.packages.dispatch.spec import ToolBuildSpec

    runtime, body_calls = _build_runtime(allow=True)
    desc = next(d for d in runtime.tools() if d.name == "call")
    spec = ToolBuildSpec(
        app=runtime,
        router=None,
        meta=desc._meta,  # noqa: SLF001 -- mirrors mcp/server.py:_build_one_tool,
    )
    chained = fold_pipeline(desc.fn, spec=spec, pipeline=DISPATCH_PIPELINE)
    result = await chained(x=11)
    assert result == {"x": 11}
    assert body_calls == [11]


async def test_mcp_authorize_with_di_denies_when_policy_denies() -> None:
    from a2kit.exceptions import AuthorizationDenied
    from a2kit.packages.dispatch import DISPATCH_PIPELINE, fold_pipeline
    from a2kit.packages.dispatch.spec import CapturedError, ToolBuildSpec

    runtime, body_calls = _build_runtime(allow=False)
    desc = next(d for d in runtime.tools() if d.name == "call")
    spec = ToolBuildSpec(
        app=runtime,
        router=None,
        meta=desc._meta,  # noqa: SLF001 -- mirrors mcp/server.py:_build_one_tool,
    )
    chained = fold_pipeline(desc.fn, spec=spec, pipeline=DISPATCH_PIPELINE)
    import pytest

    # ErrorCaptureStage wraps the AuthorizationDenied; on the MCP transport
    # the substrate's error-render stage unwraps and renders. Here we exercise
    # the pipeline-only fold, so we see the CapturedError envelope directly.
    with pytest.raises(CapturedError) as exc_info:
        await chained(x=13)
    assert isinstance(exc_info.value.__cause__, AuthorizationDenied)
    assert body_calls == [], "tool body MUST NOT run when authorize denied"
