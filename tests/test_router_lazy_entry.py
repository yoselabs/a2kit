"""BDD contract for consolidate-lifecycle-on-async-cm-protocol task 1.4.

Routers enter lazily on first dispatch of any of their tools. Routers
whose tools are never dispatched never enter. Once entered, routers
stay entered until App ``__aexit__``.
"""

from __future__ import annotations

import pytest

import a2kit
from a2kit.runtime import build
from a2kit.testing import app_of
from a2kit.testing import client as _testing_client


@pytest.mark.asyncio
async def test_router_does_not_enter_on_app_aenter() -> None:
    entered: list[str] = []

    class _GH(a2kit.Router):
        slug = "gh"

        async def __aenter__(self) -> _GH:
            entered.append("gh")
            return self

        async def __aexit__(self, *_exc: object) -> None: ...

        @a2kit.read()
        async def fetch(self) -> dict:  # type: ignore[override]
            return {"ok": True}

    app = app_of("x", _GH())
    async with build(app) as app:
        assert entered == []  # router did NOT enter just because app entered


@pytest.mark.asyncio
async def test_first_dispatch_enters_router_once() -> None:
    entered: list[str] = []

    class _GH(a2kit.Router):
        slug = "gh"

        async def __aenter__(self) -> _GH:
            entered.append("gh")
            return self

        async def __aexit__(self, *_exc: object) -> None: ...

        @a2kit.read()
        async def fetch(self) -> dict:  # type: ignore[override]
            return {"ok": True}

    app = app_of("x", _GH())
    async with _testing_client(app) as client:
        await client.invoke("gh_fetch")
        assert entered == ["gh"]
        await client.invoke("gh_fetch")
        assert entered == ["gh"]  # not re-entered


@pytest.mark.asyncio
async def test_unused_router_never_enters_and_never_exits() -> None:
    entered: list[str] = []
    exited: list[str] = []

    class _GH(a2kit.Router):
        slug = "gh"

        async def __aenter__(self) -> _GH:
            entered.append("gh")
            return self

        async def __aexit__(self, *_exc: object) -> None:
            exited.append("gh")

        @a2kit.read()
        async def gh_fetch(self) -> dict:  # type: ignore[override]
            return {}

    class _SL(a2kit.Router):
        slug = "sl"

        async def __aenter__(self) -> _SL:
            entered.append("sl")
            return self

        async def __aexit__(self, *_exc: object) -> None:
            exited.append("sl")

        @a2kit.read()
        async def sl_fetch(self) -> dict:  # type: ignore[override]
            return {}

    app = app_of("x", _GH(), _SL())
    async with _testing_client(app) as client:
        await client.invoke("gh_gh_fetch")

    assert entered == ["gh"]
    assert exited == ["gh"]


@pytest.mark.asyncio
async def test_router_lifespan_classmethod_rejected_at_add_router() -> None:
    """Subclasses still using the pre-v0.35 ``lifespan`` classmethod fail loud."""

    class _Legacy(a2kit.Router):
        slug = "leg"

        async def lifespan(self) -> None:  # type: ignore[override]  # ty: ignore[invalid-return-type]  # why: test fixture deliberately returns mismatched shape to exercise downstream branching
            yield

        @a2kit.read()
        async def x(self) -> dict:
            return {}  # type: ignore[override]

    with pytest.raises(TypeError) as ei:
        app_of("x", _Legacy())
    msg = str(ei.value)
    assert "lifespan" in msg
    assert "__aenter__" in msg
