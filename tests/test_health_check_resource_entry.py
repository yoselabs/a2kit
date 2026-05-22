"""Pinning test for the health-check resource-entry contract.

Per a2web round-10 feedback Friction F and the
``clarify-health-check-resource-entry`` OpenSpec change. Reading-only
spike on 2026-05-15 traced the path:

    run_checks (packages/health/__init__.py:74)
      -> _run_one_check (line 100)
          -> app._container.resolve_params(check.fn)        (line 108)
              -> Container.get(T) per kwarg
                  -> _construct                              (container.py:507)
                      -> _enter_lifecycle                    (line 530)
                          -> resource.__aenter__()

The contract: ``@app.health_check`` kwargs route through the standard
DI resolver, entering resources via ``__aenter__`` on first
resolution. Cleanup follows scope rules — SINGLETON resources exit at
app shutdown via ``Container.aclose()``, not per probe.

This test pins the behaviour so future refactors of the dispatch
path can't silently regress it (the contract lived only in an
internal docstring before this change).
"""

from __future__ import annotations

import asyncio
from typing import Any

import a2kit
from a2kit import HealthResult
from a2kit.packages.health import HEALTH_TOOL_NAME, app_version, run_checks
from a2kit.testing import client


class SpyResource:
    """A2enter / __aexit__ counters for the pinning test."""

    def __init__(self) -> None:
        self.entered = 0
        self.exited = 0

    async def __aenter__(self) -> SpyResource:
        self.entered += 1
        return self

    async def __aexit__(self, *exc: object) -> None:
        self.exited += 1


def test_first_probe_enters_singleton() -> None:
    """The first health probe to reference a singleton resource via
    its kwargs triggers ``__aenter__`` exactly once.

    Singletons do NOT exit per probe — they live until app shutdown.
    Assert ``exited == 0`` while the lifespan is still in flight.
    """
    app = a2kit.App("health-singleton-first-probe")
    spy = SpyResource()
    app.provide(SpyResource, lambda: spy)
    app._install_health_tool()

    @app.health_check
    def _probe(spy: SpyResource) -> HealthResult:
        # The presence of spy here is the assertion target: at the
        # moment the body runs, spy.entered must already be 1.
        assert spy.entered == 1
        return HealthResult.ok()

    async def go() -> Any:
        async with client(app) as c:
            result = await c.invoke(HEALTH_TOOL_NAME)
            # Inside the lifespan: singleton stays entered.
            assert spy.entered == 1
            assert spy.exited == 0
            return result

    result = asyncio.run(go())
    assert result["status"] == "ok"


def test_second_probe_reuses_cached_singleton() -> None:
    """A second health probe in the same app lifetime does not
    re-enter the singleton. Cached app-scope instance returns
    directly from ``_singletons``."""
    app = a2kit.App("health-singleton-second-probe")
    spy = SpyResource()
    app.provide(SpyResource, lambda: spy)
    app._install_health_tool()

    @app.health_check
    def _probe(spy: SpyResource) -> HealthResult:
        return HealthResult.ok()

    async def go() -> None:
        async with client(app) as c:
            await c.invoke(HEALTH_TOOL_NAME)
            await c.invoke(HEALTH_TOOL_NAME)
            # Two invocations, singleton entered once.
            assert spy.entered == 1
            assert spy.exited == 0

    asyncio.run(go())


def test_singleton_exits_at_lifespan_unwind() -> None:
    """Singleton ``__aexit__`` fires when the app's lifespan
    unwinds, not before. After ``async with client(app)`` exits,
    ``spy.exited`` should be 1."""
    app = a2kit.App("health-singleton-exit-at-lifespan")
    spy = SpyResource()
    app.provide(SpyResource, lambda: spy)
    app._install_health_tool()

    @app.health_check
    def _probe(spy: SpyResource) -> HealthResult:
        return HealthResult.ok()

    async def go() -> None:
        async with client(app) as c:
            await c.invoke(HEALTH_TOOL_NAME)
        # Outside the lifespan: cleanup stack has drained.
        assert spy.exited == 1

    asyncio.run(go())


def test_shared_singleton_across_checks_enters_once() -> None:
    """Two distinct health checks each declaring the same
    singleton kwarg share one instance; ``__aenter__`` fires
    exactly once across both."""
    app = a2kit.App("health-singleton-shared")
    spy = SpyResource()
    app.provide(SpyResource, lambda: spy)
    app._install_health_tool()

    observed: list[int] = []

    @app.health_check
    def _probe_a(spy: SpyResource) -> HealthResult:
        observed.append(id(spy))
        return HealthResult.ok()

    @app.health_check
    def _probe_b(spy: SpyResource) -> HealthResult:
        observed.append(id(spy))
        return HealthResult.ok()

    async def go() -> None:
        async with client(app) as c:
            await c.invoke(HEALTH_TOOL_NAME)
            assert spy.entered == 1
            # Both checks saw the same instance by identity.
            assert len(observed) == 2
            assert observed[0] == observed[1]

    asyncio.run(go())


def test_run_checks_directly_enters_singleton() -> None:
    """The lower-level ``run_checks(app)`` API (used by the CLI
    ``<app> health`` subcommand) follows the same contract — it
    must enter the resource via the resolver, not synthesize a
    None-shaped placeholder."""
    app = a2kit.App("health-run-checks-direct")
    spy = SpyResource()
    app.provide(SpyResource, lambda: spy)
    app._install_health_tool()

    @app.health_check
    def _probe(spy: SpyResource) -> HealthResult:
        return HealthResult.ok()

    async def go() -> dict[str, Any]:
        async with app:
            result = await run_checks(app._health, app._resolver, version=app_version(app))
            assert spy.entered == 1
            return result

    out = asyncio.run(go())
    assert out["status"] == "ok"
    # Lifespan unwound — singleton exited.
    assert spy.exited == 1
