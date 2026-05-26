"""Plugin manifest framework — declarative extension-point shape.

Ported from a2web's ``_plugin.py`` (a2web ADR-0001 Pattern 2,
``unify-plugin-manifests`` archive 2026-05-26). Each plugin file
exports one ``MANIFEST`` constant. ``load_surface(path, T, settings)``
walks ``path``, imports every module under it, reads its ``MANIFEST``,
calls the factory with capability-aware settings, and returns a
``dict[str, T]`` of ready-to-use instances. Anything whose factory
returns ``Unavailable(...)`` is dropped silently before reaching the
registry — the "not configured" state never propagates downstream.

Private (`_`-prefix) — public re-export is deferred until the first
external consumer asks. Zero a2kit-domain imports here; stdlib only.
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
from dataclasses import dataclass
from typing import TYPE_CHECKING, Generic, NamedTuple, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable

T = TypeVar("T")

_LOG = logging.getLogger("a2kit._plugin")


class Unavailable(NamedTuple):
    """Sentinel returned by a plugin factory when its capability is missing.

    Not an exception — unavailability at boot is *expected* (no API key,
    no Keychain access, etc.). Returning a value forces the call site
    to handle it; ``load_surface`` drops Unavailable entries before they
    reach the registry, so consumer code never sees them.
    """

    reason: str


@dataclass(frozen=True, slots=True)
class PluginManifest(Generic[T]):
    """One plugin's registration shape.

    Exported as ``MANIFEST = PluginManifest(...)`` at the bottom of
    each plugin file. ``load_surface`` reflects on the module to find it.
    """

    name: str
    """Stable lookup key used to pick a plugin from the registry."""

    protocol: type[T]
    """The SPI this plugin implements. Used to filter manifests when
    multiple plugin surfaces share a directory (rare; allowed)."""

    factory: Callable[..., T | Unavailable]
    """Capability-aware constructor. Receives the per-surface
    construction context (settings, config struct, ...) and returns
    either an instance of ``protocol`` or ``Unavailable(reason)``."""

    requires: tuple[str, ...] = ()
    """Documentation-only: capability keys this plugin needs. The
    factory is the authoritative check."""

    settings_prefix: str | None = None
    """When set, ``load_surface`` passes ``getattr(settings, prefix)``
    instead of the full settings. Reserved for future evolution."""

    priority: int = 0
    """Sort order for surfaces where priority matters. Higher fires
    first. ``-1`` means out-of-band — orchestrator dispatches these
    explicitly, not via iteration."""


def load_surface(
    surface_path: str,
    protocol: type[T],
    context: object,
) -> dict[str, T]:
    """Discover + instantiate every plugin in ``surface_path`` matching ``protocol``.

    ``context`` is the per-surface construction object passed to each
    factory. The framework treats it opaquely; each plugin file's
    factory declares the concrete type it expects.

    Returns ``{manifest.name: instance}``. Unavailable plugins are
    logged at INFO and dropped — they don't appear in the registry.
    Module-level side effects in plugin files break the model (every
    module gets imported at boot); architecture tests enforce that
    invariant.
    """
    pkg = importlib.import_module(surface_path)
    registry: dict[str, T] = {}
    pkg_path = getattr(pkg, "__path__", None)
    if pkg_path is None:
        _try_register(pkg, protocol, context, registry)
        return registry

    for module_info in pkgutil.iter_modules(pkg_path, prefix=f"{surface_path}."):
        module = importlib.import_module(module_info.name)
        _try_register(module, protocol, context, registry)
    return registry


def _try_register(
    module: object,
    protocol: type[T],
    context: object,
    registry: dict[str, T],
) -> None:
    manifest = getattr(module, "MANIFEST", None)
    if manifest is None:
        return  # not a plugin file — utility modules in the surface dir
    if not isinstance(manifest, PluginManifest):
        _LOG.warning(
            "plugin manifest wrong type: module=%s kind=%s",
            getattr(module, "__name__", "?"),
            type(manifest).__name__,
        )
        return
    if manifest.protocol is not protocol:
        return  # different surface in the same dir — not ours
    instance = manifest.factory(context)
    if isinstance(instance, Unavailable):
        _LOG.info(
            "plugin_unavailable surface=%s name=%s reason=%s",
            getattr(module, "__package__", "?"),
            manifest.name,
            instance.reason,
        )
        return
    registry[manifest.name] = instance


def load_surface_sorted(
    surface_path: str,
    protocol: type[T],
    context: object,
) -> list[tuple[str, T]]:
    """Like :func:`load_surface` but returns ``[(name, instance), ...]``
    sorted by descending priority. Use for surfaces where dispatch
    order matters.
    """
    pkg = importlib.import_module(surface_path)
    items: list[tuple[int, str, T]] = []
    pkg_path = getattr(pkg, "__path__", None)
    modules: list[object]
    if pkg_path is None:
        modules = [pkg]
    else:
        modules = [importlib.import_module(info.name) for info in pkgutil.iter_modules(pkg_path, prefix=f"{surface_path}.")]
    for module in modules:
        manifest = getattr(module, "MANIFEST", None)
        if manifest is None or not isinstance(manifest, PluginManifest):
            continue
        if manifest.protocol is not protocol:
            continue
        instance = manifest.factory(context)
        if isinstance(instance, Unavailable):
            _LOG.info(
                "plugin_unavailable surface=%s name=%s reason=%s",
                getattr(module, "__package__", "?"),
                manifest.name,
                instance.reason,
            )
            continue
        items.append((manifest.priority, manifest.name, instance))
    items.sort(key=lambda kv: -kv[0])
    return [(name, inst) for _prio, name, inst in items]


__all__ = ("PluginManifest", "Unavailable", "load_surface", "load_surface_sorted")
