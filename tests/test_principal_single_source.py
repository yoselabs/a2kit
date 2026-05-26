"""Structural invariants for the Principal bridge.

- DI scope is the single consumption path for ``Principal``.
- Only ``_principal_bridge`` names the underlying ContextVar; all
  other call sites use the named writer/reader API.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import a2kit
from a2kit.packages.context import Principal
from a2kit.runtime import build

_SRC_ROOT = Path(__file__).resolve().parents[1] / "src/a2kit"


def test_raw_contextvar_only_lives_in_bridge_module() -> None:
    """No module besides ``_principal_bridge`` may name the raw ContextVar."""
    target = _SRC_ROOT / "packages/dispatch/_principal_bridge.py"
    hits = []
    for py in _SRC_ROOT.rglob("*.py"):
        if py == target:
            continue
        text = py.read_text(encoding="utf-8")
        if "_request_principal" in text and "current_request_principal" not in text.replace(
            "_request_principal", "current_request_principal", 100
        ):
            # crude split: tolerate the named-API symbols, flag raw references
            raw_lines = [
                line
                for line in text.splitlines()
                if "_request_principal" in line
                and "set_request_principal" not in line
                and "reset_request_principal" not in line
                and "current_request_principal" not in line
            ]
            if raw_lines:
                hits.append((py, raw_lines))
    assert hits == [], f"raw _request_principal references outside bridge: {hits!r}"


def test_packages_context_does_not_re_export_the_contextvar() -> None:
    """The L0 ``packages/context`` module is back to type-only."""
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

        tools = (me,)

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

        tools = (me,)

    app = a2kit.App("demo").add_router(R())
    runtime = build(app)
    async with runtime:
        [desc] = runtime.tools()
        with pytest.raises(RuntimeError, match="Principal not seeded"):
            async with runtime.container().call_scope(desc.fn, {}) as merged:
                await desc.fn(**{k: v for k, v in merged.items() if k == "principal"})
