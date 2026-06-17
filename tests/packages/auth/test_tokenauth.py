"""BDD: TokenAuth lease validation end-to-end on the internal spoke app.

Per `auth-spec` (TokenAuth requirement):
- A token in the live set authenticates → `Principal` with the lease's
  scopes reaches `authorize=`.
- Revoking the token from the live set (mid-process) → next call 401,
  with no fixed TTL involved (the same token worked a call earlier).
- Missing token → 401.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

import a2kit
from a2kit.packages.auth import TokenAuth
from a2kit.packages.context import Principal
from a2kit.packages.http import build_http_app
from a2kit.runtime import build
from a2kit.testing import app_of


def _jobs_only(*, principal: Principal) -> bool:
    return "jobs" in principal.scopes


def _build_spoke_app(live: dict[str, Principal]) -> a2kit.App:
    """An App whose internal surface authenticates via a live lease table.

    `live` is the consumer-owned set: TokenAuth reads it per request via
    the `resolve` closure. The test mutates `live` to model revocation.
    """
    app = app_of("spoke-token")
    app.auth(TokenAuth(resolve=lambda tok: live.get(tok)))

    @app.api.get("/whoami", response_model=dict)
    async def whoami(*, principal: Principal) -> dict[str, str]:
        return {"subject": principal.subject}

    @app.api.get("/job", response_model=dict, authorize=_jobs_only)
    async def job(*, principal: Principal) -> dict[str, str]:
        return {"subject": principal.subject}

    return app


def _client(live: dict[str, Principal]) -> TestClient:
    runtime = build(_build_spoke_app(live))
    return TestClient(build_http_app(runtime, auth_target="internal"))


def test_live_lease_authenticates_with_its_scopes() -> None:
    live = {"lease-7": Principal(subject="job-7", scopes=frozenset({"jobs"}), claims={}, issued_by="runner")}
    client = _client(live)
    resp = client.get("/whoami", headers={"X-A2kit-Token": "lease-7"})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"subject": "job-7"}


def test_lease_scopes_reach_authorize_gate() -> None:
    """The lease's scopes flow into `authorize=` uniformly with any surface."""
    granted = {"lease-7": Principal(subject="job-7", scopes=frozenset({"jobs"}), claims={}, issued_by="runner")}
    ok = _client(granted).get("/job", headers={"X-A2kit-Token": "lease-7"})
    assert ok.status_code == 200, ok.text

    scopeless = {"lease-8": Principal(subject="job-8", scopes=frozenset(), claims={}, issued_by="runner")}
    denied = _client(scopeless).get("/job", headers={"X-A2kit-Token": "lease-8"})
    assert denied.status_code == 403, denied.text
    assert denied.json()["error"]["type"] == "AuthorizationDenied"


def test_revocation_is_immediate_no_ttl() -> None:
    """Same token: authenticates, then 401 the call after it leaves the live set."""
    live = {"lease-7": Principal(subject="job-7", scopes=frozenset({"jobs"}), claims={}, issued_by="runner")}
    client = _client(live)

    first = client.get("/whoami", headers={"X-A2kit-Token": "lease-7"})
    assert first.status_code == 200, first.text

    # Runner revokes the lease (job exited). No TTL: the very next call fails.
    del live["lease-7"]
    after = client.get("/whoami", headers={"X-A2kit-Token": "lease-7"})
    assert after.status_code == 401
    assert after.json()["error"] == "authentication_failed"


def test_missing_token_returns_401() -> None:
    client = _client({})
    resp = client.get("/whoami")
    assert resp.status_code == 401
    assert "missing" in resp.json()["reason"].lower()


def test_resolve_is_called_per_request() -> None:
    """`resolve` runs on every request (not once at build) — proves no caching."""
    calls: list[str] = []
    principal = Principal(subject="j", scopes=frozenset({"jobs"}), claims={}, issued_by="runner")

    def resolve(tok: str) -> Principal | None:
        calls.append(tok)
        return principal if tok == "t" else None

    app = app_of("spoke-count")
    app.auth(TokenAuth(resolve=resolve))

    @app.api.get("/ping", response_model=dict)
    async def ping(*, principal: Principal) -> dict[str, str]:
        return {"subject": principal.subject}

    client = TestClient(build_http_app(build(app), auth_target="internal"))
    client.get("/ping", headers={"X-A2kit-Token": "t"})
    client.get("/ping", headers={"X-A2kit-Token": "t"})
    assert calls == ["t", "t"]
