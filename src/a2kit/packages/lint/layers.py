"""The a2kit layer manifest — the internal dependency-graph DAG.

ADR 0004 tiers the *public Python surface* by audience. This manifest is
the internal sibling: it tiers the *import graph* by layer. A unit may
import only strictly-lower layers (plus its own); the `A2K-LAYER` lint
rule enforces it.

Units are the directories under `src/a2kit/packages/` plus one `core`
pseudo-unit covering the top-level `a2kit.*` modules. Intra-unit
ordering (module-against-module inside one unit) is out of scope —
a unit is one node.
"""

from __future__ import annotations

#: unit -> layer integer. A lower layer MUST NOT import a higher one.
LAYER_MANIFEST: dict[str, int] = {
    # L0 — kernel packages: foundational, depend only on each other
    # (acyclically) and on the foundational core modules below.
    "di": 0,
    "formatter": 0,
    "ldd": 0,
    "lint": 0,
    "context": 0,
    "health": 0,
    # L1 — core: the `a2kit.*` composition modules (app, tool, routers,
    # signature, metadata, ...). Imports kernel packages; imported by
    # everything above.
    "core": 1,
    # L2 — above core, below the transports: connectors and the shared
    # dispatch pipeline.
    "connections": 2,
    "dispatch": 2,
    # L3 — transport adapters.
    "cli": 3,
    "mcp": 3,
    "codemode": 3,
    "otel": 3,
    # L4 — the test surface, on top of everything.
    "testing": 4,
}

#: Foundational core modules — leaf type/exception definitions that
#: import nothing and that any unit may depend on. Treating them as
#: layer-exempt targets keeps a kernel package's `from a2kit.exceptions
#: import ...` from reading as an upward `core` edge. They are the
#: bedrock below every layer.
FOUNDATIONAL_CORE_MODULES = frozenset(
    {
        "a2kit.exceptions",
        "a2kit._context_protocol",
    }
)

#: Public re-export facade modules — exempt from both `A2K-LAYER` and
#: `A2K-PKG-FRONT-DOOR`. They exist to surface deeper layers as a flat
#: public API, so they import "upward" and reach past front doors by
#: design. The package root `__init__.py` files are skipped separately
#: (a re-export boundary, not a layer participant).
FACADE_MODULES = (
    # The public test-surface shim — re-exports `packages/testing` and
    # its `client` submodule as the Tier-2 `a2kit.testing` API.
    "src/a2kit/testing.py",
    "a2kit/testing.py",
)


def unit_for_module(dotted: str) -> str | None:
    """Resolve a dotted module name to its layer-manifest unit.

    ``a2kit.packages.X[.sub]`` -> ``X``; any other ``a2kit.*`` -> ``core``.
    Non-``a2kit`` modules -> ``None`` (not a layered unit).
    """
    if dotted != "a2kit" and not dotted.startswith("a2kit."):
        return None
    parts = dotted.split(".")
    if len(parts) >= 3 and parts[1] == "packages":
        return parts[2]
    return "core"


def unit_for_path(filename: str) -> str | None:
    """Resolve a source-file path to its layer-manifest unit.

    A file under ``a2kit/packages/X/`` -> ``X``; any other file under
    ``a2kit/`` -> ``core``. Files outside an ``a2kit/`` source tree -> ``None``.
    """
    norm = filename.replace("\\", "/")
    if "a2kit/" not in norm:
        return None
    tail = norm.split("a2kit/", 1)[1]
    parts = tail.split("/")
    if len(parts) >= 2 and parts[0] == "packages":
        return parts[1]
    return "core"


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
