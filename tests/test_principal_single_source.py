"""Structural invariants for the Principal bridge.

- DI scope is the single consumption path for ``Principal``.
- Principal-carrying state flows through the unified
  ``a2kit.packages.context.request_scope`` bridge; no dedicated
  ``_principal_bridge`` module remains.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import a2kit
from a2kit.packages.context import Principal
from a2kit.runtime import build

_SRC_ROOT = Path(__file__).resolve().parents[1] / "src/a2kit"


def test_legacy_principal_bridge_module_is_gone() -> None:
    """The deprecation shim was deleted in favour of `request_scope`."""
    assert not (_SRC_ROOT / "packages/dispatch/_principal_bridge.py").exists()


def test_packages_context_does_not_re_export_a_raw_principal_contextvar() -> None:
    """The L0 ``packages/context`` does not surface a raw Principal var."""
    import a2kit.packages.context as ctx_pkg

    assert "_a2kit_request_principal" not in ctx_pkg.__all__
    assert not hasattr(ctx_pkg, "_a2kit_request_principal")


@pytest.mark.asyncio
async def test_di_principal_provider_flows_to_tool_body() -> None:
    """A registered DI provider for ``Principal`` reaches a tool body
    typed ``principal: Principal``.
    """
    fake = Principal(
        subject="alice",
        scopes=frozenset({"read"}),
        claims={},
        issued_by="test",
        raw_token=None,
    )

    class R(a2kit.Router):
        slug = "demo"

        @a2kit.read()
        async def me(self, *, principal: Principal) -> dict[str, str]:
            return {"subject": principal.subject}

    app = a2kit.App("demo").add_router(R())
    app.container().provide(Principal, lambda: fake)
    runtime = build(app)
    async with runtime:
        [desc] = runtime.tools()
        async with runtime.container().call_scope(desc.fn, {}) as merged:
            result = await desc.fn(**{k: v for k, v in merged.items() if k == "principal"})
    assert result == {"subject": "alice"}


@pytest.mark.asyncio
async def test_no_provider_and_no_substrate_write_raises_clear_error() -> None:
    """No DI provider, no substrate publication → clear error, no fallback."""

    class R(a2kit.Router):
        slug = "demo"

        @a2kit.read()
        async def me(self, *, principal: Principal) -> dict[str, str]:
            return {"subject": principal.subject}

    app = a2kit.App("demo").add_router(R())
    runtime = build(app)
    async with runtime:
        [desc] = runtime.tools()
        with pytest.raises(RuntimeError, match="Principal not seeded"):
            async with runtime.container().call_scope(desc.fn, {}) as merged:
                await desc.fn(**{k: v for k, v in merged.items() if k == "principal"})
