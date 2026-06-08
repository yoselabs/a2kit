"""App DI + singleton basics.

v0.35 consolidate-lifecycle-on-async-cm-protocol: the lifespan=
constructor argument, ``Router.lifespan`` classmethod, ``app.lifespan_cm()``,
``a2kit.lifespan.compose``, and ``app.warm_async_singletons`` are removed.
The lifespan / lifecycle coverage previously here is now split between:

- ``tests/test_app_async_cm.py`` — App is its own async context manager
- ``tests/test_singleton_type_inference.py`` — three registration shapes
- ``tests/test_singleton_lifecycle_detection.py`` — auto-detected cleanup
- ``tests/test_router_lazy_entry.py`` — Router ``__aenter__`` on first dispatch
- ``tests/test_lifecycle_topology.py`` — DI-graph topological ordering
- ``tests/test_lifecycle_migration_errors.py`` — removed-surface migration hints

This file retains the sync DI and singleton-registration tests that are
independent of the lifecycle plumbing.
"""

from __future__ import annotations

from typing import Any

import pytest

from a2kit.app import App
from a2kit.packages.di._introspection import UnresolvableType
from a2kit.testing import app_of


async def _get(app: App, type_: type) -> Any:
    return await app.container().get(type_)


class _State:
    def __init__(self, label: str = "x") -> None:
        self.label = label


class _Settings:
    pass


class _Store:
    def __init__(self, settings: _Settings) -> None:
        self.settings = settings


# ----- Section 1: sync resolve end-to-end ------------------------------- #


async def test_resolve_simple_chain() -> None:
    app = app_of("t").provide(_Settings, lambda: _Settings()).provide(_Store, _Store)
    store = await _get(app, _Store)
    assert isinstance(store, _Store)
    assert isinstance(store.settings, _Settings)


def test_container_is_non_optional_after_construction() -> None:
    app = app_of("t")
    c = app.container()
    assert c is not None
    assert app.container() is c


async def test_resolve_unresolvable_raises() -> None:
    app = app_of("t")
    with pytest.raises(UnresolvableType):
        await _get(app, _Settings)


# ----- Section 2: singletons -------------------------------------------- #


async def test_singleton_method_form_caches() -> None:
    calls = {"n": 0}

    def factory() -> _State:
        calls["n"] += 1
        return _State(f"build{calls['n']}")

    app = app_of("t").provide(_State, factory)
    a = await _get(app, _State)
    b = await _get(app, _State)
    assert a is b
    assert calls["n"] == 1


async def test_singleton_class_as_factory_form() -> None:
    """``app.provide(T)`` (no factory) registers T as its own factory.

    Class-as-factory uses ``T.__init__`` at resolve time and chains DI for
    any annotated constructor parameters.
    """
    app = app_of("t").provide(_State)
    s = await _get(app, _State)
    assert isinstance(s, _State)


async def test_two_apps_independent_singletons() -> None:
    app_a = app_of("a").provide(_State, lambda: _State("A"))
    app_b = app_of("b").provide(_State, lambda: _State("B"))
    sa = await _get(app_a, _State)
    sb = await _get(app_b, _State)
    assert sa is not sb
    assert sa.label == "A"
    assert sb.label == "B"


def test_singleton_async_factory_accepted_at_registration() -> None:
    """Async singleton factories are accepted; awaited on first resolution."""

    async def factory() -> _State:
        return _State("async")

    app = app_of("t")
    app.provide(_State, factory)
    assert app.has_provider(_State)


async def test_singleton_chain_with_provide() -> None:
    def make_store(settings: _Settings) -> _Store:
        return _Store(settings)

    app = app_of("t").provide(_Settings, lambda: _Settings()).provide(_Store, make_store)
    a = await _get(app, _Store)
    b = await _get(app, _Store)
    assert a is b
    assert isinstance(a.settings, _Settings)


async def test_provide_last_write_wins() -> None:
    app = app_of("t").provide(_State, lambda: _State("via_first")).provide(_State, lambda: _State("via_second"))
    a = await _get(app, _State)
    b = await _get(app, _State)
    assert a is b
    assert a.label == "via_second"
