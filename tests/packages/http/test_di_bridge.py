"""BDD: FastAPI `Security`/`Depends` resolves a2kit DI through the bridge.

`bridge-container-fastapi-depends`: a route whose `Security` guard takes
a container-known `Database` must resolve `db` from the active a2kit
call scope, and the same SINGLETON instance must be visible to the route
handler that also injects `Database` via a2kit DI.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Security
from fastapi.testclient import TestClient

import a2kit
from a2kit.packages.http.build import build_http_app
from a2kit.runtime import build


class _Database:
    def __init__(self) -> None:
        self.name = "live-db"


def _guard(db: Annotated[_Database, Depends(_Database)]) -> str:
    # FastAPI keys this Depends off the `_Database` callable (class-as-dep).
    # The bridge installs `app.dependency_overrides[_Database] =
    # container.expose_as_fastapi_depends(_Database)` so FastAPI routes to
    # the a2kit-scoped instance instead of constructing a new one.
    return f"guarded:{db.name}"


class TestHttpDiBridge:
    def test_security_guard_resolves_a2kit_db_and_route_sees_same_instance(self) -> None:
        app = a2kit.App("bridge-test").provide(_Database, _Database)

        @app.api.get("/me", response_model=dict)
        async def me(
            *,
            authz: Annotated[str, Security(_guard)],
            db: _Database,
        ) -> dict[str, str]:
            return {"authz": authz, "db_name": db.name}

        runtime = build(app)
        fastapi_app = build_http_app(runtime)
        client = TestClient(fastapi_app)
        resp = client.get("/me")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["authz"] == "guarded:live-db"
        assert body["db_name"] == "live-db"
