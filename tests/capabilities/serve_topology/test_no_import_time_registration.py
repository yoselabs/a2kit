"""Capability: surface packages have NO import-time registration side effect.

Per `bootstrap-surfaces-explicit` (2026-05-26): `import a2kit.packages.mcp`
and `import a2kit.packages.http` MUST NOT mutate any module-level registry.
Composition happens explicitly at `a2kit.compose_default_surfaces()` time.
"""

from __future__ import annotations

import subprocess
import sys


def _run_subprocess(code: str) -> tuple[int, str, str]:
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode, result.stdout, result.stderr


def test_importing_mcp_alone_does_not_populate_registry() -> None:
    """A fresh interpreter that imports only `a2kit.packages.mcp` sees no
    active registry — the package import is now pure (no side effects).
    """
    code = """
import a2kit.packages.mcp  # no side effect expected
from a2kit.packages.dispatch.surface import current_registry
reg = current_registry()
assert reg is None, f"expected None active registry, got {reg!r}"
print("OK")
"""
    rc, out, err = _run_subprocess(code)
    assert rc == 0, f"subprocess failed: rc={rc} stdout={out!r} stderr={err!r}"
    assert out.strip() == "OK"


def test_importing_http_alone_does_not_populate_registry() -> None:
    """Same invariant for the HTTP surface package."""
    code = """
import a2kit.packages.http  # no side effect expected
from a2kit.packages.dispatch.surface import current_registry
reg = current_registry()
assert reg is None, f"expected None active registry, got {reg!r}"
print("OK")
"""
    rc, out, err = _run_subprocess(code)
    assert rc == 0, f"subprocess failed: rc={rc} stdout={out!r} stderr={err!r}"
    assert out.strip() == "OK"


def test_importing_both_surfaces_does_not_populate_registry() -> None:
    """Importing both surface packages still produces no registration."""
    code = """
import a2kit.packages.http
import a2kit.packages.mcp
from a2kit.packages.dispatch.surface import current_registry
reg = current_registry()
assert reg is None, f"expected None active registry, got {reg!r}"
print("OK")
"""
    rc, out, err = _run_subprocess(code)
    assert rc == 0, f"subprocess failed: rc={rc} stdout={out!r} stderr={err!r}"
    assert out.strip() == "OK"
