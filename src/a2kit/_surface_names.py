"""Kernel-layer registry of registered Surface names.

This module exists so the authoring layer (``_verbs.py``, L2) can ask
"what surface names are currently registered?" without importing the
dispatch layer (L4) — that edge would violate ``A2K-LAYER``. The
dispatch ``SurfaceRegistry.register_surface()`` calls
:func:`register_surface_name` as a side-effect so the kernel name list
stays in lockstep with the instance registry.

Only the *names* live here. ``Surface`` instances, ``reserved_types``,
substrate dependency markers etc. remain in
``a2kit.packages.dispatch.surface``.
"""

from __future__ import annotations

_REGISTERED_SURFACE_NAMES: list[str] = []


def register_surface_name(name: str) -> None:
    """Append ``name`` to the kernel name registry, idempotently.

    Called as a side-effect of
    ``SurfaceRegistry.register_surface`` after its duplicate-name guard
    has succeeded, so a name only ever lands here once.
    """
    if name not in _REGISTERED_SURFACE_NAMES:
        _REGISTERED_SURFACE_NAMES.append(name)


def registered_surface_names() -> tuple[str, ...]:
    """Return the registered surface names in registration order."""
    return tuple(_REGISTERED_SURFACE_NAMES)


__all__ = ["register_surface_name", "registered_surface_names"]
