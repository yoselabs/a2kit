"""``a2kit.AppBuilder`` / ``a2kit.App`` — the builder / runtime split.

Covers the ``app-builder-runtime`` capability: composition happens on a
mutable ``AppBuilder``; ``build()`` seals it into a mutation-free
``App``; direct ``App`` construction and post-seal mutation crash loud.
See ADR 0016.
"""

from __future__ import annotations

import asyncio

import click
import pytest

import a2kit


class _Probe(a2kit.Router):
    slug = "_probe"

    @a2kit.read()
    async def get(self, *, connection: str = "default") -> dict:
        return {"connection": connection}

    tools = (get,)


class _PerCall:
    """Per-call-scoped dependency (module scope so annotations resolve)."""


class _AppScopeNeedsPerCall:
    """App-scope factory that illegally depends on a per-call type."""

    def __init__(self, dep: _PerCall) -> None:
        self.dep = dep


# --------------------------- builder composition --------------------------- #


def test_builder_verbs_chain() -> None:
    """Each composition verb returns the AppBuilder for chaining."""
    builder = a2kit.AppBuilder("svc")
    assert builder.add_router(_Probe()) is builder
    assert builder.provide(int, lambda: 1) is builder


def test_add_router_registers_router_and_tools() -> None:
    app = a2kit.AppBuilder("p").add_router(_Probe()).build()
    assert len(app.routers()) == 1
    assert len(app.tools()) == 1


def test_add_cli_appends() -> None:
    @click.group()
    def my_group() -> None:
        pass

    app = a2kit.AppBuilder("p").add_cli(my_group).build()
    assert app.cli_extras() == [my_group]


def test_add_mcp_middleware_appends() -> None:
    sentinel = object()
    app = a2kit.AppBuilder("p").add_mcp_middleware(sentinel).build()
    assert app.mcp_middlewares() == [sentinel]


# ------------------------------ build / seal ------------------------------- #


def test_build_yields_a_sealed_app() -> None:
    app = a2kit.AppBuilder("svc").build()
    assert isinstance(app, a2kit.App)


def test_build_is_terminal_builder_is_spent() -> None:
    """A builder produces exactly one App; a second build() raises."""
    builder = a2kit.AppBuilder("svc")
    builder.build()
    with pytest.raises(TypeError, match="spent"):
        builder.build()


def test_composition_verb_after_build_raises() -> None:
    """A spent builder rejects further composition."""
    builder = a2kit.AppBuilder("svc")
    builder.build()
    with pytest.raises(TypeError, match="spent"):
        builder.add_router(_Probe())


def test_build_validates_provider_graph() -> None:
    """build() rejects an app-scope factory that depends on a per-call type."""
    builder = a2kit.AppBuilder("svc")
    builder.provide(_PerCall, per_call=True)
    builder.provide(_AppScopeNeedsPerCall)
    with pytest.raises(TypeError, match="scope violation"):
        builder.build()


def test_health_router_installed_by_build() -> None:
    """A builder with a registered health_check carries _meta into the App."""
    builder = a2kit.AppBuilder("svc")

    @builder.health_check
    async def _probe() -> a2kit.HealthResult:
        return a2kit.HealthResult.ok()

    app = builder.build()
    assert any(r.slug == "_meta" for r in app.routers())


# --------------------------- sealed runtime App ---------------------------- #


def test_direct_app_construction_raises() -> None:
    """`a2kit.App("svc")` is rejected — compose via AppBuilder."""
    with pytest.raises(TypeError, match="AppBuilder"):
        a2kit.App("svc")


@pytest.mark.parametrize(
    "verb",
    ["add_router", "add_cli", "add_mcp_middleware", "provide", "health_check"],
)
def test_composition_verb_absent_from_sealed_app(verb: str) -> None:
    """Composition verbs raise a migration hint on a built App."""
    app = a2kit.AppBuilder("svc").build()
    with pytest.raises(TypeError, match="AppBuilder"):
        getattr(app, verb)


def test_sealed_app_has_no_use_method() -> None:
    """Polymorphic `use` never existed and still does not — plain AttributeError."""
    app = a2kit.AppBuilder("p").build()
    assert not hasattr(app, "use")


def test_sealed_app_unknown_attr_is_attributeerror() -> None:
    """Non-verb misses stay AttributeError so getattr/hasattr behave."""
    app = a2kit.AppBuilder("p").build()
    assert not hasattr(app, "connect")
    assert getattr(app, "version", "DEFAULT") == "DEFAULT"


def test_sealed_app_is_an_async_context_manager() -> None:
    """A built App still enters/exits its lifecycle."""
    app = a2kit.AppBuilder("p").add_router(_Probe()).build()

    async def go() -> None:
        async with app as entered:
            assert entered is app

    asyncio.run(go())


# ----------------------- test overrides are re-build ----------------------- #


def test_reregistered_provider_wins_last_write() -> None:
    """provide() is last-write-wins — the override mechanism (ADR 0016)."""

    class _Service:
        def __init__(self, tag: str = "real") -> None:
            self.tag = tag

    builder = a2kit.AppBuilder("svc")
    builder.provide(_Service, lambda: _Service("real"))
    builder.provide(_Service, lambda: _Service("fake"))
    app = builder.build()
    resolved = asyncio.run(app.container().get(_Service))
    assert resolved.tag == "fake"


def test_no_post_seal_override_surface_on_container() -> None:
    """The snapshot/restore test-override seam was deleted (ADR 0016)."""
    container = a2kit.AppBuilder("svc").build().container()
    for removed in ("_override", "_snapshot", "_restore"):
        assert not hasattr(container, removed)


# --------------------------- LDD kill-switch ------------------------------- #


def test_ldd_defaults_enabled() -> None:
    app = a2kit.AppBuilder("p").build()
    assert app.ldd_reports is True
    assert app.ldd_events is True


def test_set_ldd_disables_reports() -> None:
    app = a2kit.AppBuilder("p").build().set_ldd(reports=False)
    assert app.ldd_reports is False
    assert app.ldd_events is True


def test_set_ldd_disables_events() -> None:
    app = a2kit.AppBuilder("p").build().set_ldd(events=False)
    assert app.ldd_events is False
    assert app.ldd_reports is True


def test_set_ldd_chainable() -> None:
    app = a2kit.AppBuilder("p").build()
    assert app.set_ldd(reports=False) is app


def test_set_ldd_none_keeps_existing() -> None:
    app = a2kit.AppBuilder("p").build().set_ldd(reports=False, events=False)
    app.set_ldd(reports=True)  # only flips reports
    assert app.ldd_reports is True
    assert app.ldd_events is False


def test_env_var_off_disables_both(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("A2KIT_LDD", "off")
    app = a2kit.AppBuilder("p").build()
    assert app.ldd_reports is False
    assert app.ldd_events is False


def test_env_var_unset_default_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("A2KIT_LDD", raising=False)
    app = a2kit.AppBuilder("p").build()
    assert app.ldd_reports is True
    assert app.ldd_events is True
