"""Section 4 of `a2web-feedback-round-2`: health probe.

Gherkin scenarios (mirroring `specs/health-probe/spec.md`):

  Scenario: health tool returns ok with version
    GIVEN App(name, health_tool=True) with no registered checks
    WHEN _meta.health is invoked
    THEN response = {"status": "ok", "version": <ver>, "checks": []}

  Scenario: health tool not registered by default
    GIVEN App(name) (no health_tool=)
    THEN _meta.health is absent from app.tools()

  Scenario: passing check contributes ok entry
    GIVEN @app.health_check returning HealthResult.ok()
    THEN response.checks contains {name, status="ok"}

  Scenario: failing check flips status to degraded
    GIVEN @app.health_check returning HealthResult.fail("reason")
    THEN response.status == "degraded" and the entry has reason

  Scenario: _meta.* namespace reserved
    GIVEN @a2kit.read(name="_meta.custom") on a user tool
    THEN ValueError at decoration time
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

import a2kit
from a2kit.packages.health import HEALTH_TOOL_NAME, HealthResult
from a2kit.testing import client


def test_health_tool_not_registered_by_default() -> None:
    app = a2kit.App("plain")
    names = [d.name for d in app.tools()]
    assert HEALTH_TOOL_NAME not in names


def test_health_tool_registered_when_enabled() -> None:
    app = a2kit.App("with-health")
    app._install_health_tool()
    names = [d.name for d in app.tools()]
    assert HEALTH_TOOL_NAME in names


def test_health_check_auto_enables_health_tool() -> None:
    """v0.33: first `@app.health_check` auto-installs `_meta.health`."""
    app = a2kit.App("auto-enable")

    @app.health_check
    async def _check() -> HealthResult:
        return HealthResult.ok()

    names = [d.name for d in app.tools()]
    assert HEALTH_TOOL_NAME in names


def test_health_tool_kwarg_removed_raises_with_hint() -> None:
    """v0.35: ``App(health_tool=True)`` raises TypeError with migration hint."""
    with pytest.raises(TypeError) as ei:
        a2kit.App("x", health_tool=True)  # type: ignore[call-arg]
    msg = str(ei.value)
    assert "health_tool" in msg
    assert "health_check" in msg


def test_health_check_idempotent_with_explicit_install() -> None:
    """Explicit ``_install_health_tool()`` + ``@app.health_check`` does not double-install."""
    app = a2kit.App("both")
    app._install_health_tool()  # noqa: SLF001 -- test seam

    @app.health_check
    async def _check() -> HealthResult:
        return HealthResult.ok()

    # Exactly one `_meta.health` descriptor — no duplicate router install.
    names = [d.name for d in app.tools()]
    assert names.count(HEALTH_TOOL_NAME) == 1


def test_health_cmd_does_not_import_testing_package() -> None:
    """v0.33: `<app> health` runs without importing `a2kit.packages.testing`.

    The CLI builder's ``health_cmd`` is decoupled from the test client so
    fresh non-dev installs don't crash on a missing ``pytest`` dependency.
    """
    import importlib
    import sys

    # Drop any prior import of the testing package so we can detect a fresh load.
    for mod in list(sys.modules):
        if mod.startswith("a2kit.packages.testing"):
            del sys.modules[mod]

    builder = importlib.import_module("a2kit.packages.cli.builder")
    # The function source must not reference the testing module.
    import inspect

    src = inspect.getsource(builder._register_health)
    assert "a2kit.packages.testing" not in src
    assert "from a2kit.packages.health import app_version, run_checks" in src


def test_health_returns_ok_with_no_checks() -> None:
    app = a2kit.App("with-health")
    app._install_health_tool()

    async def go() -> Any:
        async with client(app) as c:
            return await c.invoke(HEALTH_TOOL_NAME)

    result = asyncio.run(go())
    assert result["status"] == "ok"
    assert result["checks"] == []
    assert "version" in result


def test_passing_check_contributes_ok_entry() -> None:
    app = a2kit.App("with-health")
    app._install_health_tool()

    @app.health_check
    def _sqlite_ok() -> HealthResult:
        return HealthResult.ok()

    async def go() -> Any:
        async with client(app) as c:
            return await c.invoke(HEALTH_TOOL_NAME)

    result = asyncio.run(go())
    assert result["status"] == "ok"
    assert any(e["name"] == "_sqlite_ok" and e["status"] == "ok" for e in result["checks"])


def test_failing_check_flips_status_to_degraded() -> None:
    app = a2kit.App("with-health")
    app._install_health_tool()

    @app.health_check
    async def _broken() -> HealthResult:
        return HealthResult.fail("sqlite missing")

    async def go() -> Any:
        async with client(app) as c:
            return await c.invoke(HEALTH_TOOL_NAME)

    result = asyncio.run(go())
    assert result["status"] == "degraded"
    failing = next(e for e in result["checks"] if e["name"] == "_broken")
    assert failing["status"] == "fail"
    assert failing["reason"] == "sqlite missing"


def test_mixed_checks_yield_degraded() -> None:
    app = a2kit.App("with-health")
    app._install_health_tool()

    @app.health_check
    def _ok() -> HealthResult:
        return HealthResult.ok()

    @app.health_check
    def _bad() -> HealthResult:
        return HealthResult.fail("nope")

    async def go() -> Any:
        async with client(app) as c:
            return await c.invoke(HEALTH_TOOL_NAME)

    result = asyncio.run(go())
    assert result["status"] == "degraded"
    statuses = {e["name"]: e["status"] for e in result["checks"]}
    assert statuses == {"_ok": "ok", "_bad": "fail"}


def test_meta_namespace_reserved_for_user_tools() -> None:
    """User tools cannot claim a `_meta.*` name (exercised via the internal helper)."""
    from a2kit._verbs import _read_internal

    with pytest.raises(ValueError, match="reserved"):

        @_read_internal("_meta.custom")
        async def custom() -> dict:
            return {}


def test_meta_health_name_allowed_for_builtin() -> None:
    """The internal builtin tool with name `_meta.health` decorates without error."""
    app = a2kit.App("with-health")
    app._install_health_tool()
    names = [d.name for d in app.tools()]
    assert HEALTH_TOOL_NAME in names


def test_health_result_classmethods() -> None:
    ok = HealthResult.ok()
    assert ok.status == "ok"
    assert ok.reason is None
    bad = HealthResult.fail("disk full")
    assert bad.status == "fail"
    assert bad.reason == "disk full"


def test_health_result_lazy_reexport() -> None:
    """`a2kit.HealthResult` resolves via lazy __getattr__ without pulling fastmcp."""
    assert a2kit.HealthResult is HealthResult
