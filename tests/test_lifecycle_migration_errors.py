"""Post-sweep contract for the lifecycle-era tombstones (prune-stale-tombstones).

The ``lifespan=`` / ``teardown=`` kwargs and the ``Router.lifespan``
classmethod were removed in v0.35-0.36 — past the migration horizon.
Under the tombstone sunset rule (``AGENTS.md`` §1) their bespoke hints
are swept: the kwargs fall through to the generic unexpected-kwarg
``TypeError``, and a ``lifespan`` classmethod is no longer special-cased.
Still loud, no alias, no transitional period — just no bespoke hint.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import pytest

import a2kit
from a2kit.testing import app_of


def test_app_lifespan_kwarg_raises_generic_unexpected_kwarg() -> None:
    @asynccontextmanager
    async def cm(_app):  # type: ignore[no-untyped-def]
        yield

    with pytest.raises(TypeError) as ei:
        app_of("x", lifespan=cm)  # type: ignore[call-arg]
    msg = str(ei.value)
    assert "unexpected keyword" in msg
    assert "lifespan" in msg
    assert "CHANGELOG" in msg
    assert "__aenter__" not in msg


def test_singleton_teardown_kwarg_raises_generic_unexpected_kwarg() -> None:
    class _R:
        def close(self) -> None: ...

    app = app_of("x")
    with pytest.raises(TypeError) as ei:
        app.provide(_R, teardown=lambda r: r.close())  # type: ignore[call-arg]
    msg = str(ei.value)
    assert "unexpected keyword" in msg
    assert "teardown" in msg
    assert "__aexit__" not in msg


def test_router_lifespan_classmethod_no_longer_special_cased() -> None:
    """A ``lifespan`` method is now an ordinary (inert) method — the
    framework detects the async-CM protocol via ``__aenter__``/``__aexit__``
    only, so a stray ``lifespan`` no longer triggers a bespoke rejection."""

    class _R(a2kit.Router):
        slug = "r"

        async def lifespan(self) -> None:  # type: ignore[override]  # ty: ignore[invalid-return-type]  # why: legacy method name, now inert; exercised to prove it is not special-cased
            yield

        @a2kit.read()
        async def x(self) -> dict:  # type: ignore[override]
            return {}

    app = app_of("x", _R())
    assert any(r.slug == "r" for r in app._routers.all())


def test_unknown_app_kwarg_raises_standard_message() -> None:
    with pytest.raises(TypeError) as ei:
        app_of("x", totally_unknown=True)  # type: ignore[call-arg]
    msg = str(ei.value)
    assert "totally_unknown" in msg


def test_a2kit_lifespan_module_removed() -> None:
    with pytest.raises(ImportError):
        import a2kit.lifespan  # noqa: F401  # ty: ignore[unresolved-import]  # why: test exercises a removed/migrated import path to assert it raises
