"""Standalone-shippable DI package — sync legacy + async scoped lifecycle.

Two surface layers coexist during the v0.36 transition:

- Legacy: ``register`` / ``register_singleton`` / ``resolve`` / ``aresolve`` /
  ``apply_kwargs`` — sync-friendly path used by the existing dispatcher.
- New (di-scoped-lifecycle): ``provide(scope=...)`` / async ``get(T)`` /
  ``child()`` / ``aclose`` / ``__aenter__`` / ``__aexit__`` plus the
  :class:`Scope` enum and :class:`Resolver` protocol.

Future extraction to a standalone PyPI package: this directory contains
NO ``from a2kit.*`` imports outside ``a2kit.packages.di``. See
``test_no_a2kit_imports_inside_di_package``.
"""

from __future__ import annotations

from a2kit.packages.di._lazy import Lazy
from a2kit.packages.di.container import (
    Container,
    Factory,
    UnresolvableType,
    container_dispatch,
    container_dispatch_async,
)
from a2kit.packages.di.resolver import Resolver
from a2kit.packages.di.scope import Scope

__all__ = [
    "Container",
    "Factory",
    "Lazy",
    "Resolver",
    "Scope",
    "UnresolvableType",
    "container_dispatch",
    "container_dispatch_async",
]
