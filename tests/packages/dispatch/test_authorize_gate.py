"""BDD: `AuthorizeGateStage` / HTTP gate denies based on `authorize=`.

A tool with `authorize=lambda *, principal: "admin" in principal.scopes`
must deny a non-admin Principal on both substrates: HTTP returns 403, MCP
emits the documented `AuthorizationDenied` envelope, and the tool body is
never invoked.
"""

from __future__ import annotations

from typing import Annotated

import pytest
from fastapi import Security
from fastapi.testclient import TestClient

from a2kit.exceptions import AuthorizationDenied
from a2kit.packages.context import Principal, request_scope
from a2kit.packages.dispatch import DISPATCH_PIPELINE, AuthorizeGateStage, _run_authorize_gate
from a2kit.packages.dispatch.spec import ToolBuildSpec
from a2kit.packages.http.build import build_http_app
from a2kit.runtime import build
from a2kit.testing import app_of


def _admin_only(*, principal: Principal) -> bool:
    return "admin" in principal.scopes


def _guard_returns_reader() -> Principal:
    return Principal(subject="u1", scopes=frozenset({"reader"}))


class TestHttpAuthorizeDenies403:
    def test_admin_only_denies_non_admin(self) -> None:
        body_calls: list[int] = []
        app = app_of("authz-http")

        @app.api.get("/admin", response_model=dict, authorize=_admin_only)
        async def admin(*, _authz: Annotated[Principal, Security(_guard_returns_reader)]) -> dict[str, str]:
            body_calls.append(1)
            return {"ok": "yes"}

        runtime = build(app)
        client = TestClient(build_http_app(runtime))
        resp = client.get("/admin")
        assert resp.status_code == 403, resp.text
        body = resp.json()
        assert body["error"]["type"] == "AuthorizationDenied"
        assert body["error"]["kind"] == "auth"
        assert body_calls == []


class TestAuthorizeGatePipelinePlacement:
    def test_pipeline_inserts_authorize_after_dispatch_hook(self) -> None:
        names = [s.__class__.__name__ for s in DISPATCH_PIPELINE]
        assert "DispatchHookStage" in names
        assert "AuthorizeGateStage" in names
        assert names.index("AuthorizeGateStage") == names.index("DispatchHookStage") + 1


class TestRunAuthorizeGate:
    async def test_falsy_return_raises_authorization_denied(self) -> None:
        app = app_of("authz-direct")
        runtime = build(app)
        token = request_scope.publish(Principal(subject="u1", scopes=frozenset()))
        try:
            with pytest.raises(AuthorizationDenied) as exc:
                await _run_authorize_gate(_admin_only, runtime.container())
        finally:
            request_scope.reset(token)
        assert exc.value.callable_name.endswith("_admin_only")

    async def test_truthy_return_allows(self) -> None:
        app = app_of("authz-direct-allow")
        runtime = build(app)
        token = request_scope.publish(Principal(subject="u1", scopes=frozenset({"admin"})))
        try:
            await _run_authorize_gate(_admin_only, runtime.container())  # no raise
        finally:
            request_scope.reset(token)


class TestAuthorizeGateStageSelfSkips:
    def test_no_authorize_returns_fn_unchanged(self) -> None:
        async def _body() -> None:
            return None

        stage = AuthorizeGateStage()
        spec = ToolBuildSpec(
            app=build(app_of("authz-skip")),
            router=None,
            meta=None,
        )
        assert stage.wrap(_body, spec) is _body
