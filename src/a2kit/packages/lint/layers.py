"""The a2kit layer manifest — the internal dependency-graph DAG.

ADR 0004 tiers the *public Python surface* by audience. This manifest is
the internal sibling: it tiers the *import graph* by layer. A unit may
import only strictly-lower layers (plus its own); the `A2K-LAYER` lint
rule enforces it.

Units are the directories under `src/a2kit/packages/` plus the top-level
`a2kit.*` modules. The top-level modules are not one undifferentiated
`core` node: they split into three ordered sub-units — `kernel` (leaf
types and helpers), `authoring` (the decoration-time surface), and
`runtime` (`app` / `AppRuntime`). The re-export facade modules
(`__init__.py`, `ldd.py`, `testing.py`) are a layer-exempt group: they
surface deeper layers as a flat public API and so import "upward" by
design. See ADR 0019.
"""

from __future__ import annotations

#: unit -> layer integer. A lower layer MUST NOT import a higher one.
LAYER_MANIFEST: dict[str, int] = {
    # L0 — kernel packages: foundational, depend only on each other
    # (acyclically) and on the foundational core modules below.
    "di": 0,
    "formatter": 0,
    "log": 0,
    "lint": 0,
    "context": 0,
    "health": 0,
    "select": 0,
    # L1-L3 — the core sub-units. The top-level `a2kit.*` modules, split
    # from one `core` pseudo-unit into three lint-enforced layers.
    # `kernel` — leaf type/helper modules importing no `a2kit` sibling.
    "kernel": 1,
    # `authoring` — the decoration-time surface (verbs, tool, routers, ...).
    "authoring": 2,
    # `runtime` — `app` (the compose-phase builder) and `AppRuntime`.
    "runtime": 3,
    # L4 — above core, below the transports: connectors and the shared
    # dispatch pipeline.
    "connections": 4,
    "dispatch": 4,
    # L5 — transport adapters.
    "cli": 5,
    "mcp": 5,
    "codemode": 5,
    "otel": 5,
    "http": 5,
    "auth": 5,
    # L6 — the test surface, on top of everything.
    "testing": 6,
}

#: Top-level `a2kit.*` module name -> core sub-unit. Every non-package,
#: non-facade module under `src/a2kit/` is assigned here; an unlisted
#: module resolves to no unit (caught by the layer-manifest test).
_KERNEL_MODULES = frozenset(
    {
        "exceptions",
        "_context_protocol",
        "metadata",
        "_list_helpers",
        "_lifecycle_helpers",
        "_field_introspect",
        "_lazy_module",
        "config",
    }
)
_AUTHORING_MODULES = frozenset(
    {
        "_verbs",
        "tool",
        "signature",
        "schema",
        "routers",
        "_verb_validators",
    }
)
_RUNTIME_MODULES = frozenset(
    {
        "app",
        "runtime",
        "__main__",
        "_log_bootstrap",
    }
)

#: Re-export facade modules — the layer-exempt group. They exist to
#: surface deeper layers as a flat public API and so import "upward" by
#: design. Resolving to no unit keeps a facade out of the layer DAG both
#: as an import source and as an import target.
_FACADE_STEMS = frozenset({"__init__", "log", "testing"})

#: Foundational core modules — leaf type/exception definitions that
#: import nothing and that any unit may depend on. Treating them as
#: layer-exempt targets keeps a kernel-layer package's `from
#: a2kit.exceptions import ...` from reading as an upward `kernel` edge.
#: They are the bedrock below every layer.
FOUNDATIONAL_CORE_MODULES = frozenset(
    {
        "a2kit.exceptions",
        "a2kit._context_protocol",
        # Reusable PEP 562 lazy-loader helper. Every package front door that
        # exposes a lazy surface (top-level `a2kit`, `packages/otel`, etc.)
        # imports `lazy_attr` from here; the helper sits below every layer
        # so those imports don't read as upward edges.
        "a2kit._lazy_module",
    }
)

#: Public re-export facade modules — exempt from both `A2K-LAYER` and
#: `A2K-PKG-FRONT-DOOR`. They surface deeper layers as a flat public API,
#: so they import "upward" and reach past front doors by design.
FACADE_MODULES = (
    "src/a2kit/__init__.py",
    "a2kit/__init__.py",
    "src/a2kit/log.py",
    "a2kit/log.py",
    "src/a2kit/testing.py",
    "a2kit/testing.py",
)


def _core_subunit(stem: str) -> str | None:
    """Resolve a top-level module stem to its core sub-unit, or ``None``.

    ``None`` covers the layer-exempt facade modules (and any unlisted
    module — surfaced by the layer-manifest coverage test).
    """
    if stem in _KERNEL_MODULES:
        return "kernel"
    if stem in _AUTHORING_MODULES:
        return "authoring"
    if stem in _RUNTIME_MODULES:
        return "runtime"
    return None


def unit_for_module(dotted: str) -> str | None:
    """Resolve a dotted module name to its layer-manifest unit.

    ``a2kit.packages.X[.sub]`` -> ``X``; a top-level ``a2kit.<mod>`` ->
    its core sub-unit (``kernel`` / ``authoring`` / ``runtime``); a
    facade module or the bare ``a2kit`` package -> ``None``. Non-``a2kit``
    modules -> ``None`` (not a layered unit).
    """
    if dotted != "a2kit" and not dotted.startswith("a2kit."):
        return None
    parts = dotted.split(".")
    if len(parts) >= 3 and parts[1] == "packages":
        return parts[2]
    stem = parts[1] if len(parts) >= 2 else "__init__"
    return _core_subunit(stem)


def unit_for_path(filename: str) -> str | None:
    """Resolve a source-file path to its layer-manifest unit.

    A file under ``a2kit/packages/X/`` -> ``X``; a top-level file
    ``a2kit/<mod>.py`` -> its core sub-unit; a facade module -> ``None``.
    Files outside an ``a2kit/`` source tree -> ``None``.
    """
    norm = filename.replace("\\", "/")
    if "a2kit/" not in norm:
        return None
    tail = norm.split("a2kit/", 1)[1]
    parts = tail.split("/")
    if len(parts) >= 2 and parts[0] == "packages":
        return parts[1]
    stem = parts[0].removesuffix(".py")
    return _core_subunit(stem)


def layer_of(unit: str | None) -> int | None:
    """The layer integer for ``unit``, or ``None`` when unassigned."""
    if unit is None:
        return None
    return LAYER_MANIFEST.get(unit)


__all__ = [
    "FACADE_MODULES",
    "FOUNDATIONAL_CORE_MODULES",
    "LAYER_MANIFEST",
    "layer_of",
    "unit_for_module",
    "unit_for_path",
]
