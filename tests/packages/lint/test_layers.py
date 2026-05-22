"""The layer manifest — coverage and unit resolution."""

from __future__ import annotations

from pathlib import Path

from a2kit.packages.lint.layers import LAYER_MANIFEST, layer_of, unit_for_module, unit_for_path

_REPO_ROOT = Path(__file__).resolve().parents[3]


def test_manifest_covers_every_package_plus_core() -> None:
    pkg_dir = _REPO_ROOT / "src" / "a2kit" / "packages"
    dirs = {p.name for p in pkg_dir.iterdir() if p.is_dir() and p.name != "__pycache__"}
    for name in dirs:
        assert name in LAYER_MANIFEST, f"package {name!r} missing from LAYER_MANIFEST"
    assert "core" in LAYER_MANIFEST
    assert set(LAYER_MANIFEST) == dirs | {"core"}, "LAYER_MANIFEST has stale or missing units"


def test_core_sits_between_kernel_and_transports() -> None:
    core = LAYER_MANIFEST["core"]
    for kernel in ("di", "formatter", "ldd", "health", "lint"):
        assert LAYER_MANIFEST[kernel] < core, f"{kernel} should be below core"
    for transport in ("cli", "mcp", "codemode", "otel"):
        assert LAYER_MANIFEST[transport] > core, f"{transport} should be above core"


def test_unit_for_module_resolves_packages_and_core() -> None:
    assert unit_for_module("a2kit.packages.di.container") == "di"
    assert unit_for_module("a2kit.packages.mcp") == "mcp"
    assert unit_for_module("a2kit.app") == "core"
    assert unit_for_module("a2kit") == "core"
    assert unit_for_module("os") is None
    assert unit_for_module("pydantic.fields") is None


def test_unit_for_path_resolves_packages_and_core() -> None:
    assert unit_for_path("src/a2kit/packages/di/container.py") == "di"
    assert unit_for_path("src/a2kit/packages/mcp/server.py") == "mcp"
    assert unit_for_path("src/a2kit/app.py") == "core"
    assert unit_for_path("/abs/path/tests/foo.py") is None


def test_layer_of_returns_none_for_unknown_unit() -> None:
    assert layer_of("core") == LAYER_MANIFEST["core"]
    assert layer_of("not-a-unit") is None
    assert layer_of(None) is None
