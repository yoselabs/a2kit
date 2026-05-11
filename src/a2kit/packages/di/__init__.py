"""Synchronous, feature-agnostic DI container.

The container is a typed map plus parameter-annotation chain resolution.
It knows nothing about specific features (no ``"connection"``, no
``"tenant"``, no feature-name strings anywhere). Async resource lifecycle
lives outside the container — either at the app composition root (lifespan
pattern) or inside resource classes (lazy-init pattern).

Wire-input transformation (e.g. resolving a ``connection: str`` to a typed
``ConnectionConfig``) happens at the dispatch hook seam in the consumer
package (``a2kit.packages.connections``), not in the container.

See ``openspec/specs/request-scoped-di/spec.md`` and
``openspec/specs/di-container-package/spec.md`` for the binding contract.
"""

from __future__ import annotations

from a2kit.packages.di.container import (
    Container,
    Factory,
    UnresolvableType,
    container_dispatch,
)

__all__ = [
    "Container",
    "Factory",
    "UnresolvableType",
    "container_dispatch",
]
