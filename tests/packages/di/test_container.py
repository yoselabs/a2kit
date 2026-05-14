"""BDD baseline for retire-legacy-di-surface (v0.38).

Each legacy method must raise TypeError with a migration hint naming the
v0.38 replacement. Surface inventory pins the public attribute set.
"""

from __future__ import annotations

import pytest

from a2kit.packages.di.container import Container


class _T:
    pass


def test_register_raises_with_v038_hint() -> None:
    c = Container()
    with pytest.raises(TypeError, match=r"v0\.38.*provide|provide.*v0\.38") as ei:
        c.register(_T)
    assert "Container.provide" in str(ei.value)


def test_register_singleton_raises_with_v038_hint() -> None:
    c = Container()
    with pytest.raises(TypeError) as ei:
        c.register_singleton(_T, lambda: _T())
    msg = str(ei.value)
    assert "v0.38" in msg
    assert "provide" in msg


def test_resolve_sync_raises_with_v038_hint() -> None:
    c = Container()
    with pytest.raises(TypeError) as ei:
        c.resolve(_T)
    msg = str(ei.value)
    assert "v0.38" in msg
    assert "await Container.get" in msg or "await container.get" in msg.lower()


@pytest.mark.asyncio
async def test_aresolve_raises_with_v038_hint() -> None:
    c = Container()
    with pytest.raises(TypeError) as ei:
        await c.aresolve(_T)
    msg = str(ei.value)
    assert "v0.38" in msg
    assert "Container.get" in msg


def test_has_raises_with_v038_hint() -> None:
    c = Container()
    with pytest.raises(TypeError) as ei:
        c.has(_T)
    msg = str(ei.value)
    assert "v0.38" in msg
    assert "has_provider" in msg


def test_has_async_singleton_raises_with_v038_hint() -> None:
    c = Container()
    with pytest.raises(TypeError) as ei:
        c.has_async_singleton(_T)
    assert "v0.38" in str(ei.value)


def test_has_any_async_singletons_raises_with_v038_hint() -> None:
    c = Container()
    with pytest.raises(TypeError) as ei:
        c.has_any_async_singletons()
    assert "v0.38" in str(ei.value)


def test_new_surface_present() -> None:
    """The v0.36+ resolution surface is present on Container."""
    for name in (
        "provide",
        "has_provider",
        "providers_view",
        "get",
        "resolve_params",
        "dispatch",
        "child",
        "aclose",
    ):
        assert hasattr(Container, name), f"missing surface member: {name}"
