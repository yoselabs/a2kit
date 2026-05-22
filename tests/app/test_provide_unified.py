"""BDD: unified ``app.provide(T, factory, per_call=False)`` surface.

Covers spec ``app-singletons``/``request-scoped-di``: ``provide`` is the
single registration API on App. ``per_call=False`` (default) = app-scope
cached; ``per_call=True`` = fresh per dispatch. Last-write-wins re-registration
is the override mechanism. The container seals against further ``provide`` calls
after ``__aenter__``.
"""

from __future__ import annotations

import pytest

import a2kit
from a2kit.runtime import build


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
    """``app.provide(T)`` without ``per_call`` caches across dispatches."""
    app = a2kit.App("test")
    app.provide(_State)

    async with build(app) as app:
        async with app._resolver.child() as call1:
            a = await call1.get(_State)
        async with app._resolver.child() as call2:
            b = await call2.get(_State)

    assert a is b, "app-scope (default) returned distinct instances across calls"
    assert _State.instances_created == 1


@pytest.mark.asyncio
async def test_provide_per_call_true_opts_in() -> None:
    """``app.provide(T, per_call=True)`` produces a fresh instance each dispatch."""
    app = a2kit.App("test")
    app.provide(_State, per_call=True)

    async with build(app) as app:
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

    app = a2kit.App("test")
    app.provide(_State, async_factory, per_call=True)

    async with build(app) as app:
        async with app._resolver.child() as call1:
            await call1.get(_State)
        async with app._resolver.child() as call2:
            await call2.get(_State)

    assert counter["awaited"] == 2, "async per-call factory not awaited per dispatch"


@pytest.mark.asyncio
async def test_re_registration_last_write_wins() -> None:
    """``app.provide(T, ...)`` called twice — second registration wins, no warning."""

    class _Repo:
        def __init__(self, impl: _Real | _Fake) -> None:
            self.impl = impl

    app = a2kit.App("test")
    app.provide(_Real, lambda: _Real(), per_call=False)
    app.provide(_Fake, lambda: _Fake(), per_call=False)
    # First registration of the repo binds to _Real:
    app.provide(_Repo, lambda: _Repo(_Real()))
    # Second registration overrides to _Fake — composition-root override pattern.
    app.provide(_Repo, lambda: _Repo(_Fake()))

    async with build(app) as app:
        repo = await app._resolver.get(_Repo)

    assert repo.impl.label == "fake", "re-registration did not override prior provider"


def test_unannotated_factory_error_names_provide() -> None:
    """An unannotated factory raises a TypeError naming the live `app.provide`,
    not the removed `app.singleton`."""
    app = a2kit.App("test")

    def make_state():  # noqa: ANN202 -- the missing return annotation is the point
        return _State()

    with pytest.raises(TypeError) as excinfo:
        app.provide(make_state)
    msg = str(excinfo.value)
    assert "app.provide" in msg, f"error must name the live method: {msg!r}"
    assert "app.singleton" not in msg, f"error names the removed method: {msg!r}"


def test_runtime_container_is_sealed() -> None:
    """A finisher's ``build()`` seals the runtime container against ``provide(...)``.

    The App's own compose-phase container stays mutable; only the
    snapshotted runtime container is sealed.
    """
    app = a2kit.App("test")
    app.provide(_State)

    runtime = build(app)
    with pytest.raises(TypeError) as excinfo:
        runtime._container.provide(_Real)  # noqa: SLF001 -- exercising the seal
    msg = str(excinfo.value)
    assert "sealed" in msg.lower(), f"sealed-container error message missing context: {msg!r}"

    # The App stays a reusable builder — its compose container is not sealed.
    app.provide(_Real)
    assert app.has_provider(_Real)
