"""The layer manifest — coverage, ordering, and unit resolution.

Post `split-app-runtime`: the top-level `a2kit.*` modules are no longer
one `core` pseudo-unit; they split into three ordered sub-units —
`kernel` < `authoring` < `runtime` — with the re-export facades
(`__init__.py`, `ldd.py`, `testing.py`) layer-exempt. See ADR 0019.
"""

from __future__ import annotations

from pathlib import Path

from a2kit.packages.lint.layers import (
    LAYER_MANIFEST,
    _AUTHORING_MODULES,
    _FACADE_STEMS,
    _KERNEL_MODULES,
    _RUNTIME_MODULES,
    layer_of,
    unit_for_module,
    unit_for_path,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CORE_SUBUNITS = ("kernel", "authoring", "runtime")


def test_manifest_covers_every_package_plus_core_subunits() -> None:
    pkg_dir = _REPO_ROOT / "src" / "a2kit" / "packages"
    dirs = {p.name for p in pkg_dir.iterdir() if p.is_dir() and p.name != "__pycache__"}
    for name in dirs:
        assert name in LAYER_MANIFEST, f"package {name!r} missing from LAYER_MANIFEST"
    for subunit in _CORE_SUBUNITS:
        assert subunit in LAYER_MANIFEST, f"core sub-unit {subunit!r} missing from LAYER_MANIFEST"
    assert "core" not in LAYER_MANIFEST, "the `core` pseudo-unit was split into kernel/authoring/runtime"
    assert set(LAYER_MANIFEST) == dirs | set(_CORE_SUBUNITS), "LAYER_MANIFEST has stale or missing units"


def test_core_subunits_are_ordered_kernel_below_authoring_below_runtime() -> None:
    assert LAYER_MANIFEST["kernel"] < LAYER_MANIFEST["authoring"]
    assert LAYER_MANIFEST["authoring"] < LAYER_MANIFEST["runtime"]


def test_authoring_above_kernel_packages_and_below_transports() -> None:
    authoring = LAYER_MANIFEST["authoring"]
    for kernel_pkg in ("di", "formatter", "log", "health", "lint"):
        assert LAYER_MANIFEST[kernel_pkg] < authoring, f"{kernel_pkg} should be below authoring"
    for transport in ("cli", "mcp", "codemode", "otel"):
        assert LAYER_MANIFEST[transport] > authoring, f"{transport} should be above authoring"


def test_every_top_level_module_is_assigned_a_subunit_or_facade() -> None:
    """No top-level `a2kit.*` module may be unaccounted for in the manifest."""
    src_dir = _REPO_ROOT / "src" / "a2kit"
    stems = {p.stem for p in src_dir.glob("*.py")}
    assigned = _KERNEL_MODULES | _AUTHORING_MODULES | _RUNTIME_MODULES | _FACADE_STEMS
    unaccounted = stems - assigned
    assert not unaccounted, f"top-level modules missing from the layer manifest: {sorted(unaccounted)}"


def test_unit_for_module_resolves_packages_and_core_subunits() -> None:
    assert unit_for_module("a2kit.packages.di.container") == "di"
    assert unit_for_module("a2kit.packages.mcp") == "mcp"
    assert unit_for_module("a2kit.app") == "runtime"
    assert unit_for_module("a2kit.runtime") == "runtime"
    assert unit_for_module("a2kit.metadata") == "kernel"
    assert unit_for_module("a2kit.routers") == "authoring"
    assert unit_for_module("os") is None
    assert unit_for_module("pydantic.fields") is None


def test_unit_for_path_resolves_packages_and_core_subunits() -> None:
    assert unit_for_path("src/a2kit/packages/di/container.py") == "di"
    assert unit_for_path("src/a2kit/packages/mcp/server.py") == "mcp"
    assert unit_for_path("src/a2kit/app.py") == "runtime"
    assert unit_for_path("src/a2kit/runtime.py") == "runtime"
    assert unit_for_path("src/a2kit/_verbs.py") == "authoring"
    assert unit_for_path("src/a2kit/exceptions.py") == "kernel"
    assert unit_for_path("/abs/path/tests/foo.py") is None


def test_facade_modules_are_layer_exempt() -> None:
    """The re-export facades resolve to no unit — they sit outside the DAG."""
    assert unit_for_module("a2kit") is None
    assert unit_for_module("a2kit.ldd") is None
    assert unit_for_module("a2kit.testing") is None
    assert unit_for_path("src/a2kit/__init__.py") is None
    assert unit_for_path("src/a2kit/ldd.py") is None
    assert unit_for_path("src/a2kit/testing.py") is None


def test_layer_of_returns_none_for_unknown_unit() -> None:
    assert layer_of("runtime") == LAYER_MANIFEST["runtime"]
    assert layer_of("not-a-unit") is None
    assert layer_of(None) is None
