"""Mirror tests for `a2kit.packages.mcp.principal_middleware`."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from a2kit.packages.context import Principal, _a2kit_request_principal
from a2kit.packages.mcp.principal_middleware import PrincipalMiddleware, _principal_from_context


def test_principal_from_context_handles_direct_principal_attribute() -> None:
    p = Principal(subject="u1", scopes=frozenset({"x"}))
    ctx = SimpleNamespace(principal=p)
    assert _principal_from_context(ctx) is p


def test_principal_from_context_synthesizes_from_access_token() -> None:
    token = SimpleNamespace(client_id="u2", scopes=["a", "b"], claims={"k": 1}, issuer="iss")
    ctx = SimpleNamespace(access_token=token, principal=None)
    result = _principal_from_context(ctx)
    assert result is not None
    assert result.subject == "u2"
    assert result.scopes == frozenset({"a", "b"})
    assert result.issued_by == "iss"


def test_principal_from_context_returns_none_when_unauthenticated() -> None:
    assert _principal_from_context(None) is None
    assert _principal_from_context(SimpleNamespace()) is None


@pytest.mark.asyncio
async def test_middleware_sets_and_resets_contextvar() -> None:
    seen: list[Principal | None] = []

    async def _call_next(_ctx: Any) -> None:
        seen.append(_a2kit_request_principal.get())

    p = Principal(subject="u1", scopes=frozenset())
    middleware_ctx = SimpleNamespace(fastmcp_context=SimpleNamespace(principal=p))
    await PrincipalMiddleware().on_call_tool(middleware_ctx, _call_next)  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]  # why: SimpleNamespace stub for MiddlewareContext duck-typing
    assert seen == [p]
    assert _a2kit_request_principal.get() is None
