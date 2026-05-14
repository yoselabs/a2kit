"""BDD contract for consolidate-lifecycle-on-async-cm-protocol task 1.6.

Removed surfaces raise ``TypeError`` with embedded migration hints
naming the replacement path. No alias, no DeprecationWarning, no
transitional period (per CLAUDE.md "no backward compat shims").
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import pytest

import a2kit


def test_app_lifespan_kwarg_raises_with_hint() -> None:
    @asynccontextmanager
    async def cm(_app):  # type: ignore[no-untyped-def]
        yield

    with pytest.raises(TypeError) as ei:
        a2kit.App("x", lifespan=cm)  # type: ignore[call-arg]
    msg = str(ei.value)
    assert "lifespan=" in msg
    assert "__aenter__" in msg


def test_singleton_teardown_kwarg_raises_with_hint() -> None:
    class _R:
        def close(self) -> None: ...

    app = a2kit.App("x")
    with pytest.raises(TypeError) as ei:
        app.singleton(_R, teardown=lambda r: r.close())  # type: ignore[call-arg]
    msg = str(ei.value)
    assert "teardown=" in msg
    assert "__aexit__" in msg


def test_router_lifespan_classmethod_rejected_at_add_router() -> None:
    class _R(a2kit.Router):
        slug = "r"

        async def lifespan(self) -> None:  # type: ignore[override]
            yield

        @a2kit.read()
        async def x(self) -> dict:  # type: ignore[override]
            return {}

        tools = (x,)

    app = a2kit.App("x")
    with pytest.raises(TypeError) as ei:
        app.add_router(_R())
    msg = str(ei.value)
    assert "lifespan" in msg
    assert "__aenter__" in msg


def test_unknown_app_kwarg_raises_standard_message() -> None:
    with pytest.raises(TypeError) as ei:
        a2kit.App("x", totally_unknown=True)  # type: ignore[call-arg]
    msg = str(ei.value)
    assert "totally_unknown" in msg


def test_a2kit_lifespan_module_removed() -> None:
    with pytest.raises(ImportError):
        import a2kit.lifespan  # noqa: F401
