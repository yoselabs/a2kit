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

import pytest

from a2kit.app import App
from a2kit.packages.di.container import UnresolvableType


class _State:
    def __init__(self, label: str = "x") -> None:
        self.label = label


class _Settings:
    pass


class _Store:
    def __init__(self, settings: _Settings) -> None:
        self.settings = settings


# ----- Section 1: sync resolve end-to-end ------------------------------- #


def test_resolve_simple_chain_sync() -> None:
    app = App("t")
    app.provide(_Settings, lambda: _Settings())
    app.provide(_Store, _Store)
    store = app.container().resolve(_Store)
    assert isinstance(store, _Store)
    assert isinstance(store.settings, _Settings)


def test_container_is_non_optional_after_construction() -> None:
    app = App("t")
    c = app.container()
    assert c is not None
    assert app.container() is c


def test_resolve_unresolvable_raises() -> None:
    app = App("t")
    with pytest.raises(UnresolvableType):
        app.container().resolve(_Settings)


# ----- Section 2: singletons -------------------------------------------- #


def test_singleton_method_form_caches() -> None:
    calls = {"n": 0}

    def factory() -> _State:
        calls["n"] += 1
        return _State(f"build{calls['n']}")

    app = App("t")
    app.provide(_State, factory)
    a = app.container().resolve(_State)
    b = app.container().resolve(_State)
    assert a is b
    assert calls["n"] == 1


def test_singleton_class_as_factory_form() -> None:
    """``app.provide(T)`` (no factory) registers T as its own factory.

    Class-as-factory uses ``T.__init__`` at resolve time and chains DI for
    any annotated constructor parameters.
    """
    app = App("t")
    app.provide(_State)
    s = app.container().resolve(_State)
    assert isinstance(s, _State)


def test_two_apps_independent_singletons() -> None:
    app_a = App("a")
    app_b = App("b")
    app_a.provide(_State, lambda: _State("A"))
    app_b.provide(_State, lambda: _State("B"))
    sa = app_a.container().resolve(_State)
    sb = app_b.container().resolve(_State)
    assert sa is not sb
    assert sa.label == "A"
    assert sb.label == "B"


def test_singleton_async_factory_accepted_at_registration() -> None:
    """Async singleton factories are accepted; awaited on first resolution."""

    async def factory() -> _State:
        return _State("async")

    app = App("t")
    app.provide(_State, factory)
    assert app.has_provider(_State)


def test_singleton_chain_with_provide() -> None:
    app = App("t")
    app.provide(_Settings, lambda: _Settings())

    def make_store(settings: _Settings) -> _Store:
        return _Store(settings)

    app.provide(_Store, make_store)
    a = app.container().resolve(_Store)
    b = app.container().resolve(_Store)
    assert a is b
    assert isinstance(a.settings, _Settings)


def test_provide_then_singleton_last_write_wins() -> None:
    app = App("t")
    app.provide(_State, lambda: _State("via_provide"))
    app.provide(_State, lambda: _State("via_singleton"))
    a = app.container().resolve(_State)
    b = app.container().resolve(_State)
    assert a is b
    assert a.label == "via_singleton"
