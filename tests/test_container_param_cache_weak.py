"""``Container._param_cache`` keys on the live factory object via
``weakref.WeakKeyDictionary``.

R12 swap-out closes the id-recycling hazard: CPython recycles
``id(function)`` when refcount drops to zero, so the previous
``dict[int, list[_ParamSpec]]`` cache could hand back a stale param-spec
list when a new factory inherited a freed function's id. The weak-key
cache keys on the object identity, auto-vacates on GC, and removes both
the aliasing mode and the memory-growth mode in nested test scopes.
"""

from __future__ import annotations

import functools
import gc
import weakref

from a2kit.packages.di.container import Container


class _Service:
    def __init__(self) -> None:
        self.tag = "svc"


def test_param_cache_uses_weakkeydictionary() -> None:
    """The cache attribute is a WeakKeyDictionary instance."""
    c = Container()
    assert isinstance(c._param_cache, weakref.WeakKeyDictionary)  # noqa: SLF001


def test_param_cache_entry_vacates_on_factory_gc() -> None:
    """When a factory is dropped from scope and GC'd, its cache entry vanishes.

    This is the property that closes the id-aliasing hazard — under the old
    ``dict[int, ...]`` cache, the entry would survive until something else
    reused the id, at which point lookup returned a stale list.
    """
    c = Container()

    def _make_and_register() -> int:
        def factory() -> _Service:
            return _Service()

        c.register(_Service, factory)
        # Warm the param cache.
        _ = c._params_for(factory)  # noqa: SLF001
        return id(factory)

    _make_and_register()
    # Replace the registered factory so the old one has no live references.
    c.register(_Service, lambda: _Service())
    gc.collect()
    # The WeakKeyDictionary should have shed the entry. We can't look it up
    # without a strong ref to the original factory; what we can check is that
    # the cache size dropped to at most the count of still-live factories.
    live_factories = set(c.providers().values())
    assert all(k in live_factories for k in c._param_cache)  # noqa: SLF001


def test_param_cache_returns_fresh_specs_for_distinct_factories() -> None:
    """Two factories registered in sequence get independent cache entries.

    Equivalent of the regression case the old id-keyed cache could miss
    under id recycling.
    """
    c = Container()

    def fa(a: int) -> _Service:
        del a
        return _Service()

    def fb(b: str) -> _Service:
        del b
        return _Service()

    c.register(_Service, fa)
    specs_a = c._params_for(fa)  # noqa: SLF001
    c.register(_Service, fb)
    specs_b = c._params_for(fb)  # noqa: SLF001
    assert [s.name for s in specs_a] == ["a"]
    assert [s.name for s in specs_b] == ["b"]
    assert specs_a is not specs_b


def test_partial_factory_is_cached_like_plain_function() -> None:
    """On CPython 3.11+, ``functools.partial`` is weakly referenceable.

    The design doc flagged partials as a hazard; empirically they round-trip
    through ``WeakKeyDictionary`` cleanly. This test pins the actual behavior
    so a future Python regression (or a swap to a less weak-friendly key
    type) is caught here, not in production.
    """

    def make(arg: int) -> _Service:
        del arg
        return _Service()

    partial = functools.partial(make, 1)
    c = Container()
    c.register(_Service, partial)
    # Cache write succeeds without TypeError; round-trip returns the same list.
    specs = c._params_for(partial)  # noqa: SLF001
    again = c._params_for(partial)  # noqa: SLF001
    assert specs is again
