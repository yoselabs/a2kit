"""Thin pytest fixtures + ``make_test_app`` DI-swap helper.

This module is intentionally tiny. ``cassette`` is a ~5-line vcrpy wrapper.
``app`` returns a fresh ``a2kit.App``. ``make_test_app`` rebuilds an App with
``Depends(factory)`` defaults replaced by ``Depends(fake)`` per the contract
verified in design.md Round 7 — DI overrides happen at construction time via
uncalled-for primitives, not via a runtime override map on App.
"""

from __future__ import annotations

import functools
import inspect
from typing import TYPE_CHECKING, Any, cast

import pytest
from uncalled_for import Depends

import a2kit
from a2kit.metadata import get_meta, set_meta
from a2kit.routers import Router

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


@pytest.fixture
def cassette(tmp_path: Path) -> Callable[..., Any]:
    """Return a factory for vcrpy cassette context managers.

    Usage in tests: ``with cassette("foo") as cm: ...`` — records on first
    run (cassette absent), replays thereafter. Pass ``record_mode=`` to
    override.
    """
    import vcr  # type: ignore[import-untyped]

    def _make(name: str, *, record_mode: str | None = None) -> Any:
        path = tmp_path / f"{name}.yaml"
        mode = record_mode if record_mode is not None else ("once" if not path.exists() else "none")
        return vcr.use_cassette(str(path), record_mode=mode)

    return _make


@pytest.fixture
def app() -> a2kit.App:
    """A fresh ``a2kit.App`` named ``"test"``."""
    return a2kit.App("test")


def _rebuild_with_overrides(fn: Callable[..., Any], overrides: dict[Callable[..., Any], Callable[..., Any]]) -> Callable[..., Any]:
    """Return a function whose ``Depends(real)`` defaults are swapped per ``overrides``.

    The new function shares the body of ``fn`` but the inspected signature
    advertises ``Depends(fake)`` so ``uncalled_for`` resolves the fake at
    call time. Metadata (``A2KitMeta``) is copied across so router/adapter
    code keeps working.
    """
    sig = inspect.signature(fn)
    new_params: list[inspect.Parameter] = []
    changed = False
    for param in sig.parameters.values():
        default = param.default
        factory = getattr(default, "factory", None)
        if factory is not None and factory in overrides:
            new_default = Depends(overrides[factory])
            new_params.append(param.replace(default=new_default))
            changed = True
        else:
            new_params.append(param)
    if not changed:
        return fn

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return fn(*args, **kwargs)

    # why: functools.wraps returns _Wrapped which doesn't expose __signature__ in stubs
    cast("Any", wrapper).__signature__ = sig.replace(parameters=new_params)
    meta = get_meta(fn)
    if meta is not None:
        set_meta(wrapper, meta)
    return wrapper


class _OverrideRouter(Router):
    """Router whose tool list is supplied directly (post-override)."""

    def __init__(
        self,
        slug: str,
        tools: list[Callable[..., Any]],
    ) -> None:
        # Bypass Router.__init__ — it walks class attributes for @tool methods.
        self.slug = slug
        self._tools = list(tools)


def make_test_app(
    routers: list[Router],
    *,
    overrides: dict[Callable[..., Any], Callable[..., Any]] | None = None,
    name: str = "test",
) -> a2kit.App:
    """Build an ``App`` whose Depends factories are swapped per ``overrides``.

    Each entry in ``overrides`` maps a real factory to a fake factory. For
    every tool function on every router, parameters whose default is
    ``Depends(real)`` are rewritten to ``Depends(fake)``. The new functions
    are wrapped in lightweight routers that preserve the original slugs.

    Returns a fresh ``a2kit.App`` with the rewritten routers attached.
    """
    overrides = overrides or {}
    test_app = a2kit.App(name)
    for router in routers:
        rewritten = [_rebuild_with_overrides(fn, overrides) for fn in router.tools()]
        if not overrides:
            # Keep original Router instance; nothing to swap.
            test_app.use(router)
            continue
        test_app.use(_OverrideRouter(router.slug, rewritten))
    return test_app


__all__ = ["app", "cassette", "make_test_app"]
