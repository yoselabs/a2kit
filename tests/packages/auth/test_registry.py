"""BDD: `App.auth(spec)` accumulator + AppRuntime exposure.

Per `auth-spec`: multiple registrations accumulate in registration
order. `runtime.auth_registry` exposes the materialised list.
"""

from __future__ import annotations

from a2kit.packages.auth import ApiKey, APIKeyAuth
from a2kit.runtime import build
from a2kit.testing import app_of


def test_app_auth_registers_and_accumulates_in_order() -> None:
    app = app_of("auth-accum")
    a = APIKeyAuth(keys=[ApiKey("a", "alice")])
    b = APIKeyAuth(keys=[ApiKey("b", "bob")], header="X-Alt-Key")
    app.auth(a)
    app.auth(b)
    specs = app.auth_registry.all()
    assert specs == (a, b)


def test_no_auth_call_leaves_registry_none() -> None:
    app = app_of("no-auth")
    assert app.auth_registry is None


def test_runtime_carries_auth_registry() -> None:
    app = app_of("auth-rt")
    app.auth(APIKeyAuth(keys=[ApiKey("k", "alice")]))
    runtime = build(app)
    assert runtime.auth_registry is app.auth_registry


def test_for_target_filters_by_surface() -> None:
    app = app_of("auth-target")
    api_spec = APIKeyAuth(keys=[ApiKey("k", "alice")])
    app.auth(api_spec)
    api_specs = app.auth_registry.for_target("api")
    mcp_specs = app.auth_registry.for_target("mcp")
    assert api_specs == (api_spec,)
    assert mcp_specs == ()
