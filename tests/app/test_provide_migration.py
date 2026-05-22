"""BDD: migration errors for removed ``singleton`` surface.

Covers spec ``app-singletons``: ``app.singleton(...)``, ``app.has_singleton(...)``,
and ``app.singletons()`` are removed in v0.36 and SHALL raise ``TypeError``
(or ``AttributeError``) with migration hints naming the replacement.
"""

from __future__ import annotations

import pytest

import a2kit


class _State:
    pass


def test_singleton_raises_with_hint() -> None:
    """``app.singleton(T, factory)`` is gone; raises with migration hint."""
    app = a2kit.AppBuilder("test").build()

    with pytest.raises(TypeError) as excinfo:
        app.singleton(_State, _State)

    msg = str(excinfo.value)
    assert "singleton" in msg, "migration error must name the removed method"
    assert "AppBuilder" in msg, "migration error must name the replacement"
    assert "v0.40" in msg, "migration error must name the removal version"


def test_has_singleton_raises_with_hint() -> None:
    """``app.has_singleton(T)`` is gone; raises with migration hint to ``has_provider``."""
    app = a2kit.AppBuilder("test").build()

    with pytest.raises(TypeError) as excinfo:
        app.has_singleton(_State)

    msg = str(excinfo.value)
    assert "has_singleton" in msg
    assert "AppBuilder" in msg
    assert "v0.40" in msg


def test_singletons_raises_with_hint() -> None:
    """``app.singletons()`` is gone; raises on a built App."""
    app = a2kit.AppBuilder("test").build()

    with pytest.raises(AttributeError) as excinfo:
        app.singletons()

    msg = str(excinfo.value)
    assert "singletons" in msg
