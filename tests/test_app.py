"""``a2kit.App`` — the compose-phase builder.

Covers the ``core-composition`` capability: composition happens on a
pure, reusable ``a2kit.App``; a finisher's internal ``build(app)`` step
snapshots it into an ``AppRuntime``; composition after a build affects
only subsequent builds. ``App`` is the one public type; ``build`` is
finisher-internal. See ADR 0019 (supersedes ADR 0017).
"""

from __future__ import annotations

import asyncio

import click
import pytest

import a2kit
from a2kit.testing import app_of


class _Probe(a2kit.Router):
    slug = "_probe"

    @a2kit.read()
    async def get(self, *, connection: str = "default") -> dict:
        return {"connection": connection}


class _PerCall:
    """Per-call-scoped dependency (module scope so annotations resolve)."""


class _AppScopeNeedsPerCall:
    """App-scope factory that illegally depends on a per-call type."""

    def __init__(self, dep: _PerCall) -> None:
        self.dep = dep


# ---------------------------- App composition ------------------------------ #


def test_app_constructed_directly() -> None:
    """`app_of("svc")` returns an App with no error."""
    assert isinstance(app_of("svc"), a2kit.App)


def test_composition_verbs_chain() -> None:
    """Each composition verb returns the App for chaining."""
    app = app_of("svc")
    assert app.provide(int, lambda: 1) is app


def test_routers_classvar_registers_router_and_tools() -> None:
    """Reference-composition via `routers=` registers the router and its tools.

    Successor to the imperative `add_router` registration coverage:
    `app_of("p", _Probe())` composes the router through the `routers`
    ClassVar (the replacement for `add_router`).
    """
    app = app_of("p", _Probe())
    assert len(app.router_instances()) == 1
    assert len(app.tools()) == 1


def test_duplicate_slug_registration_raises() -> None:
    """Composing two routers that share a slug trips the dup-slug guard.

    Successor to the imperative double-`add_router` collision coverage:
    the `routers` ClassVar walks the same `_register_router` seam, so the
    guard fires when `app_of` composes both at construction time.
    """

    class _A(a2kit.Router):
        slug = "dup"

    class _B(a2kit.Router):
        slug = "dup"

    with pytest.raises(ValueError, match="already registered"):
        app_of("t", _A(), _B())


def test_add_cli_appends() -> None:
    @click.group()
    def my_group() -> None:
        pass

    app = app_of("p").add_cli(my_group)
    assert app.cli_extras() == [my_group]


def test_add_mcp_middleware_appends() -> None:
    sentinel = object()
    app = app_of("p").add_mcp_middleware(sentinel)
    assert app.mcp_middlewares() == [sentinel]


def test_health_check_installs_meta_router() -> None:
    """Registering a health_check auto-installs the _meta router."""
    app = app_of("svc")

    @app.health_check
    async def _probe() -> a2kit.HealthResult:
        return a2kit.HealthResult.ok()

    assert any(r.slug == "_meta" for r in app.router_instances())


# ----------------------- no public AppBuilder / build ---------------------- #


def test_appbuilder_is_not_a_public_symbol() -> None:
    """`from a2kit import AppBuilder` fails — there is one type, App."""
    with pytest.raises(ImportError):
        from a2kit import AppBuilder  # noqa: F401


def test_app_has_no_public_build() -> None:
    """The App carries no public `build()` — finishers seal internally."""
    assert not hasattr(app_of("svc"), "build")


# ---------------------------- finisher build ------------------------------- #


def test_build_validates_provider_graph() -> None:
    """build() rejects an app-scope factory that depends on a per-call type."""
    from a2kit.runtime import build

    app = app_of("svc")
    app.provide(_PerCall, per_call=True)
    app.provide(_AppScopeNeedsPerCall)
    with pytest.raises(TypeError, match="scope violation"):
        build(app)


def test_app_is_reusable_across_builds() -> None:
    """One App may be built more than once — it is a pure, reusable builder."""
    from a2kit.runtime import build

    app = app_of("svc")
    first = build(app)
    second = build(app)
    assert first is not second  # each build is an independent runtime


def test_composition_verbs_callable_after_build() -> None:
    """Every composition verb stays callable after a finisher builds a runtime.

    There is no sealed mode: a verb called after ``build()`` simply
    affects the next build.
    """
    from a2kit.runtime import build

    app = app_of("svc")
    build(app)

    @click.group()
    def extra() -> None:
        pass

    # None of these raise — the App is a pure builder with no sealed mode.
    app.add_cli(extra)
    app.add_mcp_middleware(object())
    app.provide(int, lambda: 1)

    @app.health_check
    async def _probe() -> a2kit.HealthResult:
        return a2kit.HealthResult.ok()


def test_composition_after_build_affects_only_future_builds() -> None:
    """A verb called after build() reaches later builds, not the built runtime."""
    from a2kit.runtime import build

    class _Late:
        pass

    app = app_of("svc")
    runtime = build(app)
    app.provide(_Late, _Late)
    # The already-built runtime is a snapshot — it never sees the late provider.
    assert not runtime.container().has_provider(_Late)
    # A fresh build off the same App picks the late provider up.
    assert build(app).container().has_provider(_Late)


def test_composition_after_a_finisher_is_allowed() -> None:
    """After a real finisher (testing.client) runs, the App stays mutable."""
    from a2kit.testing import client

    app = app_of("svc", _Probe())

    async def go() -> None:
        async with client(app):
            pass

    asyncio.run(go())
    # No TypeError — composition affects only subsequent builds.
    app.provide(int, lambda: 1)
    assert app.has_provider(int)


# ---------------------------- runtime surface ------------------------------ #


def test_app_unknown_attr_is_attributeerror() -> None:
    """Unknown attribute access stays AttributeError so getattr/hasattr behave."""
    app = app_of("p")
    assert not hasattr(app, "use")
    assert not hasattr(app, "connect")
    assert getattr(app, "version", "DEFAULT") == "DEFAULT"


def test_app_is_not_an_async_context_manager() -> None:
    """The App is a pure builder — the lifecycle belongs to the AppRuntime."""
    app = app_of("p", _Probe())
    assert not hasattr(app, "__aenter__")
    assert not hasattr(app, "__aexit__")


# ----------------------- test overrides are re-build ----------------------- #


def test_reregistered_provider_wins_last_write() -> None:
    """provide() is last-write-wins — the override mechanism (ADR 0006)."""

    class _Service:
        def __init__(self, tag: str = "real") -> None:
            self.tag = tag

    app = app_of("svc")
    app.provide(_Service, lambda: _Service("real"))
    app.provide(_Service, lambda: _Service("fake"))
    resolved = asyncio.run(app.container().get(_Service))
    assert resolved.tag == "fake"


def test_no_override_surface_on_container() -> None:
    """The snapshot/restore test-override seam was deleted (ADR 0006)."""
    container = app_of("svc").container()
    for removed in ("_override", "_snapshot", "_restore"):
        assert not hasattr(container, removed)


# --------------------------- log kill-switch ------------------------------- #


def test_log_enabled_by_default() -> None:
    app = app_of("p")
    assert app.config.log.enabled is True


def test_env_var_off_disables_emission(monkeypatch: pytest.MonkeyPatch) -> None:
    """A2KIT_LOG__ENABLED=false sets the a2kit logger to a drop-everything level."""
    import logging

    monkeypatch.setenv("A2KIT_LOG__ENABLED", "false")
    app = app_of("p")
    assert app.config.log.enabled is False
    assert logging.getLogger("a2kit").level > logging.CRITICAL


def test_env_var_unset_default_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("A2KIT_LOG__ENABLED", raising=False)
    app = app_of("p")
    assert app.config.log.enabled is True
