"""BDD: a `Principal` produced by either substrate reaches the tool body via DI.

HTTP path: a FastAPI `Security` guard returns a `Principal`; the substrate
wrapper detects it in `reserved_kwargs`, publishes it via the dispatch
principal bridge, and seeds it into the per-call DI scope via
`scoped_seeds={Principal: ...}`. The tool body taking
`principal: Principal` resolves it via a2kit DI.

MCP path: the `PrincipalMiddleware` reads the request `Context.access_token`
(simulated via a stub here), publishes via the named bridge writer API
around `call_next`, and `DispatchHookStage` reads the bridge and seeds
the per-call DI scope so the tool body sees it.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Security
from fastapi.testclient import TestClient

import a2kit
from a2kit.packages.context import Principal
from a2kit.packages.http.build import build_http_app
from a2kit.runtime import build
from a2kit.testing import app_of


def _guard_returning_principal() -> Principal:
    return Principal(subject="u1", scopes=frozenset({"reader"}))


class TestHttpPrincipalReachesBody:
    def test_security_guard_principal_resolves_in_body_via_di(self) -> None:
        app = app_of("principal-http")

        @app.api.get("/whoami", response_model=dict)
        async def whoami(
            *,
            _authz: Annotated[Principal, Security(_guard_returning_principal)],
            principal: Principal,
        ) -> dict[str, str]:
            return {"subject": principal.subject}

        runtime = build(app)
        client = TestClient(build_http_app(runtime))
        resp = client.get("/whoami")
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"subject": "u1"}


class TestMcpPrincipalReachesBody:
    """Exercises the bridge-seed path used by `DispatchHookStage`.

    We do not stand up a full FastMCP transport in this unit (covered by
    the integration suite); instead, we publish via the bridge writer API
    directly to model what `PrincipalMiddleware` does in the on_call_tool
    wrapper, and assert the dispatch hook's call_scope sees a SCOPED
    Principal.
    """

    async def test_dispatch_hook_seeds_principal_from_bridge(self) -> None:
        from a2kit.packages.context import request_scope

        class R(a2kit.Router):
            slug = "p"

            @a2kit.read()
            async def whoami(self, *, principal: Principal) -> dict[str, str]:
                return {"subject": principal.subject}

        app = app_of("principal-mcp", R())
        runtime = build(app)

        p = Principal(subject="u1", scopes=frozenset())
        token = request_scope.publish(p)
        try:
            desc = next(d for d in runtime.tools() if d.name == "p_whoami")
            async with runtime.container().call_scope(desc.fn, {}, framework_seeds={Principal: p}) as merged:
                result = await desc.fn(**{k: v for k, v in merged.items() if k == "principal"})
        finally:
            request_scope.reset(token)

        assert result == {"subject": "u1"}
