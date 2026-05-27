"""Reusable PEP 562 ``__getattr__`` helper for package-front-door lazy loading.

Each package that exposes a curated lazy surface declares its tables — a
``_LAZY_ATTRS`` dict of ``name -> (module, attr)`` for re-exports, optional
``_LAZY_MODULES`` dict of ``name -> module`` for submodule aliases, optional
``_REMOVED`` dict of ``name -> migration hint`` for cleanly-evicted names —
and binds the helpers::

    from a2kit._lazy_module import lazy_attr, lazy_dir

    __getattr__ = lazy_attr(__name__, _LAZY_ATTRS, modules=_LAZY_MODULES, removed=_REMOVED)
    __dir__ = lazy_dir(globals(), _LAZY_ATTRS, _LAZY_MODULES)

The returned ``__getattr__`` does the import-then-cache lookup; ``__dir__``
unions the static names with the lazy tables for nicer REPL completion.

This is foundational core — anything in ``a2kit.*`` may import it without
incurring a layer violation. See ``packages/lint/layers.py``.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

LazyAttrSpecs = dict[str, tuple[str, str]]
LazyModuleSpecs = dict[str, str]
RemovedHints = dict[str, str]


def lazy_attr(
    module_name: str,
    attrs: LazyAttrSpecs,
    *,
    modules: LazyModuleSpecs | None = None,
    removed: RemovedHints | None = None,
) -> Any:
    """Return a PEP 562 ``__getattr__`` resolving ``attrs`` / ``modules`` / ``removed``."""
    modules = modules or {}
    removed = removed or {}

    def __getattr__(name: str) -> Any:  # noqa: N807 -- PEP 562 module-level hook; the name is mandated by the protocol
        mod_target = modules.get(name)
        if mod_target is not None:
            return import_module(mod_target)
        spec = attrs.get(name)
        if spec is not None:
            mod, attr = spec
            return getattr(import_module(mod), attr)
        hint = removed.get(name)
        if hint is not None:
            raise AttributeError(hint)
        raise AttributeError(f"module {module_name!r} has no attribute {name!r}")

    return __getattr__


def lazy_dir(
    module_globals: dict[str, Any],
    attrs: LazyAttrSpecs,
    modules: LazyModuleSpecs | None = None,
) -> Any:
    """Return a PEP 562 ``__dir__`` unioning static globals + lazy table keys."""
    modules = modules or {}

    def __dir__() -> list[str]:  # noqa: N807 -- PEP 562 module-level hook
        return sorted({*module_globals, *attrs, *modules})

    return __dir__


__all__ = ["LazyAttrSpecs", "LazyModuleSpecs", "RemovedHints", "lazy_attr", "lazy_dir"]
