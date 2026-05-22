"""Regression guards for the import-acyclicity refactor.

Each cycle that `decouple-import-cycles` removed gets a test that fails
loudly if a future edit re-introduces the back-edge. Module-graph
assertions run in a fresh interpreter (subprocess) so a stale
``sys.modules`` from earlier in the test session cannot mask a real edge.
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
from typing import Any

import pytest

import a2kit
from a2kit import HealthResult
from a2kit.packages.health import app_version, run_checks


def _modules_after_import(import_stmt: str) -> set[str]:
    """Return ``sys.modules`` keys after running ``import_stmt`` fresh."""
    code = f"import sys\n{import_stmt}\nprint('\\n'.join(sorted(sys.modules)))"
    out = subprocess.run(  # noqa: S603
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True,
    )
    return set(out.stdout.split())


# --- cycle 1: cli <-> mcp ------------------------------------------------- #


def test_mcp_server_does_not_import_cli() -> None:
    mods = _modules_after_import("import a2kit.packages.mcp.server")
    leaked = {m for m in mods if m.startswith("a2kit.packages.cli")}
    assert not leaked, f"mcp pulled cli modules: {sorted(leaked)}"


def test_wrappers_does_not_import_cli() -> None:
    mods = _modules_after_import("import a2kit.packages.mcp._wrappers")
    leaked = {m for m in mods if m.startswith("a2kit.packages.cli")}
    assert not leaked, f"mcp._wrappers pulled cli modules: {sorted(leaked)}"


def test_context_package_is_low_level() -> None:
    """`packages/context` imports no transport package.

    Its one lawful `a2kit.packages.*` dependency is the lazy `ldd` import
    inside `_emit`; it must never reach `cli`, `mcp`, or `codemode`.
    """
    mods = _modules_after_import("import a2kit.packages.context")
    for forbidden in ("a2kit.packages.cli", "a2kit.packages.mcp", "a2kit.packages.codemode"):
        leaked = {m for m in mods if m.startswith(forbidden)}
        assert not leaked, f"context pulled {forbidden}: {sorted(leaked)}"


# --- cycle 2: mcp <-> codemode ------------------------------------------- #


def test_codemode_does_not_import_mcp_server() -> None:
    mods = _modules_after_import("import a2kit.packages.codemode")
    assert "a2kit.packages.mcp.server" not in mods


# --- cycle 3: app <-> health --------------------------------------------- #


def test_health_does_not_import_app() -> None:
    mods = _modules_after_import("import a2kit.packages.health")
    assert "a2kit.app" not in mods


# --- cycle 4 (already absent — kept as a regression guard) --------------- #


def test_packages_testing_does_not_import_core_shim() -> None:
    mods = _modules_after_import("import a2kit.packages.testing")
    assert "a2kit.testing" not in mods


# --- migration tombstones ------------------------------------------------ #


def test_old_run_code_path_raises_migration_hint() -> None:
    from a2kit.packages import codemode

    with pytest.raises(ImportError, match=r"a2kit\.packages\.cli"):
        _ = codemode.run_code


# The `StderrToolContext` tombstone is mirror-tested in
# tests/packages/cli/test_context.py (the A2K-TEST-MIRROR home for the
# tombstone module).


# --- run_checks behaviour through the Resolver seam ---------------------- #


def test_run_checks_aggregates_through_resolver() -> None:
    app = a2kit.App("acyclicity-health")
    app._install_health_tool()  # noqa: SLF001 -- exercising the lower-level seam

    @app.health_check
    def ok_probe() -> HealthResult:
        return HealthResult.ok()

    async def go() -> dict[str, Any]:
        async with app:
            registry = app._health  # noqa: SLF001 -- test seam
            resolver = app._container  # noqa: SLF001 -- test seam
            return await run_checks(registry, resolver, version=app_version(app))

    result = asyncio.run(go())
    assert result["status"] == "ok"
    assert result["checks"][0]["name"] == "ok_probe"
    assert result["checks"][0]["status"] == "ok"


def test_run_checks_version_is_caller_supplied() -> None:
    app = a2kit.App("acyclicity-health-version")
    app._install_health_tool()  # noqa: SLF001 -- exercising the lower-level seam

    async def go() -> dict[str, Any]:
        async with app:
            registry = app._health  # noqa: SLF001 -- test seam
            resolver = app._container  # noqa: SLF001 -- test seam
            return await run_checks(registry, resolver, version="9.9.9")

    result = asyncio.run(go())
    assert result["version"] == "9.9.9"
