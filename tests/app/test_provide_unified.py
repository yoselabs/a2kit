"""BDD: unified ``builder.provide(T, factory, per_call=False)`` surface.

Covers spec ``app-singletons``/``request-scoped-di``: ``provide`` is the
single registration API on AppBuilder. ``per_call=False`` (default) = app-scope
cached; ``per_call=True`` = fresh per dispatch. Last-write-wins re-registration
is the override mechanism. The container seals against further ``provide`` calls
after ``__aenter__``.
"""

from __future__ import annotations

import pytest

import a2kit


class _State:
    instances_created: int = 0

    def __init__(self) -> None:
        type(self).instances_created += 1


class _Real:
    label = "real"


class _Fake:
    label = "fake"


@pytest.fixture(autouse=True)
def _reset_counters() -> None:
    _State.instances_created = 0


@pytest.mark.asyncio
async def test_provide_default_is_app_scope() -> None:
    """``builder.provide(T)`` without ``per_call`` caches across dispatches."""
    builder = a2kit.AppBuilder("test")
    builder.provide(_State)
    app = builder.build()

    async with app:
        async with app._resolver.child() as call1:
            a = await call1.get(_State)
        async with app._resolver.child() as call2:
            b = await call2.get(_State)

    assert a is b, "app-scope (default) returned distinct instances across calls"
    assert _State.instances_created == 1


@pytest.mark.asyncio
async def test_provide_per_call_true_opts_in() -> None:
    """``builder.provide(T, per_call=True)`` produces a fresh instance each dispatch."""
    builder = a2kit.AppBuilder("test")
    builder.provide(_State, per_call=True)
    app = builder.build()

    async with app:
        async with app._resolver.child() as call1:
            a = await call1.get(_State)
        async with app._resolver.child() as call2:
            b = await call2.get(_State)

    assert a is not b, "per_call=True returned cached instance across dispatches"
    assert _State.instances_created == 2


@pytest.mark.asyncio
async def test_async_factory_accepted_on_per_call() -> None:
    """``provide(T, async_factory, per_call=True)`` accepts an async factory."""
    counter = {"awaited": 0}

    async def async_factory() -> _State:
        counter["awaited"] += 1
        return _State()

    builder = a2kit.AppBuilder("test")
    builder.provide(_State, async_factory, per_call=True)
    app = builder.build()

    async with app:
        async with app._resolver.child() as call1:
            await call1.get(_State)
        async with app._resolver.child() as call2:
            await call2.get(_State)

    assert counter["awaited"] == 2, "async per-call factory not awaited per dispatch"


@pytest.mark.asyncio
async def test_re_registration_last_write_wins() -> None:
    """``builder.provide(T, ...)`` called twice — second registration wins, no warning."""

    class _Repo:
        def __init__(self, impl: _Real | _Fake) -> None:
            self.impl = impl

    builder = a2kit.AppBuilder("test")
    builder.provide(_Real, lambda: _Real(), per_call=False)
    builder.provide(_Fake, lambda: _Fake(), per_call=False)
    # First registration of the repo binds to _Real:
    builder.provide(_Repo, lambda: _Repo(_Real()))
    # Second registration overrides to _Fake — composition-root override pattern.
    builder.provide(_Repo, lambda: _Repo(_Fake()))
    app = builder.build()

    async with app:
        repo = await app._resolver.get(_Repo)

    assert repo.impl.label == "fake", "re-registration did not override prior provider"


@pytest.mark.asyncio
async def test_sealed_after_aenter() -> None:
    """Container is sealed against ``provide(...)`` after ``async with app:`` enters."""
    builder = a2kit.AppBuilder("test")
    builder.provide(_State)
    app = builder.build()

    async with app:
        with pytest.raises(TypeError) as excinfo:
            app.provide(_Real)
        msg = str(excinfo.value)
        # Spec: message names the sealing rule and the override pattern.
        assert "sealed" in msg.lower() or "after" in msg.lower(), f"sealed-container error message missing context: {msg!r}"
