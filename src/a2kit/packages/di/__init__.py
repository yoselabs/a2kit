"""Standalone-shippable DI package.

Primary surface (v0.36+):

- ``Container.provide(t, factory, *, scope=...)`` — registration
- ``Container.call_scope(fn, wire_kwargs, *, pre_hook=None)`` — per-call DI-scope async-CM
- ``Container.resolve_params(fn)`` — DI resolution with ``Lazy[T]`` awareness
- ``Container.get(t)``, ``child()``, ``aclose()``, ``__aenter__``/``__aexit__``
- :class:`Scope`, :class:`Resolver` Protocol, :class:`Lazy` alias

Legacy surface (still present for TestClient seam + sync test paths):
``register`` / ``register_singleton`` / ``resolve`` / ``aresolve`` /
``has`` / ``has_async_singleton``. Scheduled for separate retirement.

The ``apply_kwargs`` / ``container_dispatch`` family is retired in v0.38
(dispatch routes through ``Container.dispatch`` exclusively).

Future extraction to a standalone PyPI package: this directory contains
NO ``from a2kit.*`` imports outside ``a2kit.packages.di``. See
``test_no_a2kit_imports_inside_di_package``.
"""

from __future__ import annotations

from a2kit.packages.di._helpers import lazy_inner_type
from a2kit.packages.di._lazy import Lazy
from a2kit.packages.di._request_scope import _a2kit_request_scope
from a2kit.packages.di.container import (
    Container,
    Factory,
    UnresolvableType,
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
    "_a2kit_request_scope",
    "lazy_inner_type",
]
