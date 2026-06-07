"""Capability: `expose=` validation runs at `runtime.build()` time against
the composed surface registry — NOT at decoration time. Per
`bootstrap-surfaces-explicit` (2026-05-26).
"""

from __future__ import annotations

import pytest

import a2kit
from a2kit.packages.dispatch.surface import SurfaceRegistry
from a2kit.runtime import build


def test_expose_unknown_passes_decoration_silently() -> None:
    """Decoration captures `expose=` unchanged; no name validation."""

    class R(a2kit.Router):
        slug = "demo"

        @a2kit.read(expose=("nonexistent-surface",))  # type: ignore[arg-type]
        async def t(self, *, k: str) -> dict[str, str]:
            return {"k": k}

    # Class body executed without raising; the bad name lives on the descriptor.
    app = a2kit.App("demo").add_router(R())
    [desc] = app.tools()
    assert desc.expose == ("nonexistent-surface",)


def test_expose_unknown_raises_at_build_with_composed_surfaces() -> None:
    """Build with a composed registry catches the unknown name."""

    class R(a2kit.Router):
        slug = "demo"

        @a2kit.read(expose=("typo-surface",))  # type: ignore[arg-type]
        async def t(self, *, k: str) -> dict[str, str]:
            return {"k": k}

    app = a2kit.App("demo").add_router(R())
    surfaces = a2kit.compose_default_surfaces()
    with pytest.raises(TypeError, match="typo-surface"):
        build(app, surfaces=surfaces)


def test_expose_unknown_error_lists_composed_surfaces() -> None:
    """The build-time error names the composed surface set so authors can
    self-correct without grepping a registry.
    """

    class R(a2kit.Router):
        slug = "demo"

        @a2kit.read(expose=("zzz",))  # type: ignore[arg-type]
        async def t(self, *, k: str) -> dict[str, str]:
            return {"k": k}

    app = a2kit.App("demo").add_router(R())
    surfaces = a2kit.compose_default_surfaces()
    with pytest.raises(TypeError) as exc:
        build(app, surfaces=surfaces)

    msg = str(exc.value)
    for name in ("mcp", "api"):
        assert name in msg, f"composed surface {name!r} missing from error: {msg!r}"


def test_expose_validation_runs_against_default_registry_when_no_surfaces_passed() -> None:
    """`runtime.build()` with no `surfaces=` composes the default registry
    and validates `expose=` against it — there is no longer a no-registry
    bypass.
    """

    class R(a2kit.Router):
        slug = "demo"

        @a2kit.read(expose=("nonexistent",))  # type: ignore[arg-type]
        async def t(self, *, k: str) -> dict[str, str]:
            return {"k": k}

    app = a2kit.App("demo").add_router(R())
    with pytest.raises(TypeError, match="nonexistent"):
        build(app)


def test_expose_validation_skipped_with_empty_registry() -> None:
    """Empty registry → nothing to validate against → skipped (documented)."""

    class R(a2kit.Router):
        slug = "demo"

        @a2kit.read(expose=("anything",))  # type: ignore[arg-type]
        async def t(self, *, k: str) -> dict[str, str]:
            return {"k": k}

    app = a2kit.App("demo").add_router(R())
    runtime = build(app, surfaces=SurfaceRegistry())
    assert runtime.surfaces is not None
    assert runtime.surfaces.names() == ()
