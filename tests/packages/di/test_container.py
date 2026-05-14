"""Synchronous DI container — typed providers, parameter-annotation chaining, per-call cache.

v0.27: container is sync end-to-end; async factories are rejected at
registration; ``"connection"`` is not a magic name (lives only in the
consumer's dispatch hook).
"""

from __future__ import annotations

import pytest

from a2kit.packages.di.container import Container, UnresolvableType


class _Cfg:
    def __init__(self, host: str = "localhost") -> None:
        self.host = host


class _Store:
    def __init__(self, cfg: _Cfg) -> None:
        self.cfg = cfg


def test_register_then_resolve_simple_chain() -> None:
    c = Container()
    c.register(_Cfg, lambda: _Cfg("h"))
    c.register(_Store, _Store)
    store = c.resolve(_Store)
    assert isinstance(store, _Store)
    assert store.cfg.host == "h"


def test_class_as_factory_when_factory_omitted() -> None:
    c = Container()
    c.register(_Cfg)
    c.register(_Store)
    store = c.resolve(_Store)
    assert isinstance(store, _Store)
    # _Cfg default host applies because there's no provider for str.
    assert store.cfg.host == "localhost"


def test_per_call_cache_dedupes_within_one_resolution() -> None:
    seen: list[_Cfg] = []

    def cfg_factory() -> _Cfg:
        cfg = _Cfg("x")
        seen.append(cfg)
        return cfg

    class _Audit:
        def __init__(self, cfg: _Cfg, store: _Store) -> None:
            self.cfg = cfg
            self.store = store

    c = Container()
    c.register(_Cfg, cfg_factory)
    c.register(_Store)
    c.register(_Audit)

    cache: dict = {}
    audit = c.resolve(_Audit, cache=cache)
    assert audit.cfg is audit.store.cfg
    assert len(seen) == 1


def test_unresolvable_raises_with_chain() -> None:
    c = Container()
    c.register(_Store)  # no _Cfg provider
    with pytest.raises(UnresolvableType) as ei:
        c.resolve(_Store)
    assert ei.value.type_ is _Cfg


def test_async_factory_rejected_at_registration() -> None:
    async def afactory() -> _Cfg:
        return _Cfg("a")

    c = Container()
    with pytest.raises(ValueError, match="async"):
        c.register(_Cfg, afactory)


def test_singleton_caches_across_resolves() -> None:
    seen: list[_Cfg] = []

    def factory() -> _Cfg:
        cfg = _Cfg("s")
        seen.append(cfg)
        return cfg

    c = Container()
    c.register_singleton(_Cfg, factory)
    a = c.resolve(_Cfg)
    b = c.resolve(_Cfg)
    assert a is b
    assert len(seen) == 1


def test_async_singleton_factory_accepted() -> None:
    """Singleton factories may be async; first aresolve awaits the factory.

    See `tests/test_singleton_async_factories.py` for the full async-singleton
    behaviour suite; this just pins that registration no longer raises."""

    async def afactory() -> _Cfg:
        return _Cfg()

    c = Container()
    c.register_singleton(_Cfg, afactory)
    assert c.has_singleton(_Cfg)
    assert c.has_async_singleton(_Cfg)




def test_replace_provider_last_write_wins() -> None:
    c = Container()
    c.register(_Cfg, lambda: _Cfg("first"))
    c.register(_Cfg, lambda: _Cfg("second"))
    c.register(_Store)
    s = c.resolve(_Store)
    assert s.cfg.host == "second"


def test_wire_scope_registration_is_generic() -> None:
    """Container tracks wire scopes by name; knows nothing about specific names."""
    c = Container()
    c.register_wire_scope("tenant", _Cfg)
    scopes = c.wire_scopes()
    assert "tenant" in scopes
    assert _Cfg in scopes["tenant"]


def test_wire_scopes_used_by_fn() -> None:
    c = Container()
    c.register(_Cfg)
    c.register_wire_scope("connection", _Cfg)

    def fn(*, cfg: _Cfg, n: int) -> None:  # noqa: ARG001
        return None

    assert c.wire_scopes_used_by(fn) == {"connection"}


def test_container_source_has_no_feature_names() -> None:
    """v0.27 contract: container module code is feature-agnostic.

    Docstrings and comments may *mention* example scope names ("connection")
    for clarity. The contract is about code identifiers / behavior, not prose.
    Strip docstrings and comments before checking.
    """
    import pathlib
    import re

    src = pathlib.Path(__file__).parent.parent.parent.parent / "src/a2kit/packages/di/container.py"
    text = src.read_text()
    text = re.sub(r'""".*?"""', "", text, flags=re.DOTALL)
    text = re.sub(r"'''.*?'''", "", text, flags=re.DOTALL)
    # Strip single-line `#` comments (after stripping docstrings to avoid touching docstring contents).
    text = re.sub(r"#[^\n]*", "", text)
    assert "connection" not in text.lower(), "container.py code mentions 'connection'"
    assert "tenant" not in text.lower(), "container.py code mentions 'tenant'"
    assert "tracker" not in text.lower(), "container.py code mentions 'tracker'"
