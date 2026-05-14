"""Factory + type-introspection helpers for the DI container.

Extracted from ``a2kit.packages.di.container`` per
``split-oversized-core-files`` to keep ``container.py`` under the
A2K014 SLOC budget. Pure helpers with no Container coupling.
"""

from __future__ import annotations

import inspect
import types
import typing
from collections.abc import Callable
from typing import Any, get_origin

Factory = Callable[..., Any]


class UnresolvableType(Exception):
    """Raised when the container cannot satisfy a requested type."""

    def __init__(self, type_: Any, chain: list[Any]) -> None:
        self.type_ = type_
        self.chain = list(chain)
        super().__init__(f"cannot resolve {type_!r}; chain: {self.chain}")


class _ParamSpec:
    __slots__ = ("annotation", "has_default", "name")

    def __init__(self, name: str, annotation: Any, has_default: bool) -> None:
        self.name = name
        self.annotation = annotation
        self.has_default = has_default


def _factory_callable(factory: Factory) -> Callable[..., Any]:
    """Return the introspectable callable for a factory."""
    if inspect.isclass(factory):
        return factory.__init__
    return factory


def _factory_params(factory: Factory) -> list[_ParamSpec]:
    """List the factory's input parameters (skipping ``self``)."""
    from a2kit.signature import resolve_hints

    target = _factory_callable(factory)
    hints = resolve_hints(target)
    try:
        sig = inspect.signature(target)
    except (TypeError, ValueError):
        return []
    out: list[_ParamSpec] = []
    for pname, param in sig.parameters.items():
        if pname == "self":
            continue
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue
        ann = hints.get(pname, param.annotation)
        has_default = param.default is not inspect.Parameter.empty
        out.append(_ParamSpec(pname, ann, has_default))
    return out


def _is_primitive_or_external(t: Any) -> bool:
    """Return True for types that are wire-shaped (not container-injectable)."""
    if t is inspect.Parameter.empty or t is Any:
        return True
    if t in (str, int, float, bool, bytes, type(None)):
        return True
    origin = get_origin(t)
    if origin in (list, tuple, dict, set, frozenset, type, typing.Union, types.UnionType):
        return True
    if origin is typing.Literal:
        return True
    try:
        from pydantic import BaseModel

        if inspect.isclass(t) and issubclass(t, BaseModel):
            return True
    except ImportError:
        pass
    return False


__all__ = [
    "Factory",
    "UnresolvableType",
    "_ParamSpec",
    "_factory_callable",
    "_factory_params",
    "_is_primitive_or_external",
]
