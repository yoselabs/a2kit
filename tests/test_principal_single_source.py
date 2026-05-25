"""Spec coverage for ``principal-single-source``.

Locks the two ADDED requirements:

- ``principal-propagation``: DI scope is the single source of truth for
  ``Principal``; an injected DI provider must flow through to a tool
  body without touching any contextvar.
- ``dispatch-pipeline``: ``stages.py`` source contains no read of the
  substrate contextvar ``_a2kit_request_principal``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import a2kit
from a2kit.packages.context import Principal
from a2kit.runtime import build

_STAGES_SRC = Path(__file__).resolve().parents[1] / "src/a2kit/packages/dispatch/stages.py"


def test_dispatch_stages_source_has_no_principal_contextvar_read() -> None:
    """``DispatchHookStage`` / ``AuthorizeGateStage`` / ``LddStateStage``
    live in ``stages.py``. The spec forbids any of them reading the
    substrate's request-Principal contextvar — the seeding helper in
    ``_principal_scope.py`` is the one allowed read site.
    """
    text = _STAGES_SRC.read_text(encoding="utf-8")
    assert "_a2kit_request_principal" not in text, (
        "stages.py must not reference _a2kit_request_principal directly; "
        "Principal seeding lives in dispatch/_principal_scope.py per the "
        "principal-single-source spec."
    )


@pytest.mark.asyncio
async def test_di_principal_provider_flows_to_tool_body() -> None:
    """A registered DI provider for ``Principal`` reaches a tool body
    typed ``principal: Principal`` without any contextvar interaction.
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
    """Without a DI provider AND without substrate-published Principal
    on the contextvar, a tool body declaring ``principal: Principal``
    sees no fallback path — the dispatcher must surface a clear error.
    """

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
