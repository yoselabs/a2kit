"""A3 — `a2kit.Lazy` and `a2kit.LddEmission` are top-level re-exports."""

from __future__ import annotations

import a2kit
import a2kit.packages
import a2kit.packages.di
import a2kit.packages.ldd


def test_top_level_imports_succeed() -> None:
    from a2kit import Lazy, LddEmission  # noqa: F401 -- import-side-effect verification

    assert Lazy is a2kit.packages.di.Lazy
    assert LddEmission is a2kit.packages.ldd.LddEmission


def test_legacy_paths_still_resolve_same_object() -> None:
    from a2kit import Lazy as TopLazy
    from a2kit.packages.di import Lazy as DiLazy

    assert TopLazy is DiLazy

    from a2kit import LddEmission as TopEmission
    from a2kit.packages.ldd import LddEmission as LddEmissionFromLdd

    assert TopEmission is LddEmissionFromLdd


def test_symbols_in_dir_alongside_canonical_top_level() -> None:
    surface = dir(a2kit)
    for name in ("App", "Router", "ToolContext", "HealthResult", "Lazy", "LddEmission"):
        assert name in surface, f"expected {name!r} in dir(a2kit); got: {sorted(surface)}"


def test_packages_namespace_documented_as_internal() -> None:
    doc = a2kit.packages.__doc__ or ""
    lowered = doc.lower()
    assert "internal" in lowered, "a2kit.packages docstring must declare the namespace as internal"
    assert "scaffolding" in lowered or "consumer" in lowered, "docstring must steer consumers to top-level"
    # The top-level `a2kit` package must be named as the canonical surface.
    assert "a2kit" in doc, "docstring must reference the canonical top-level `a2kit` namespace"
