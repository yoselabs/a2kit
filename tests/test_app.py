"""``a2kit.App`` — the single composition + runtime type.

Covers the ``app-builder-runtime`` capability: composition happens on a
mutable ``a2kit.App``; a finisher seals it internally; composition after
sealing crashes loud. There is one public type and no public ``build()``.
See ADR 0017 (supersedes ADR 0016).
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


# ---------------------------- App composition ------------------------------ #


def test_app_constructed_directly() -> None:
    """`a2kit.App("svc")` returns an App with no error."""
    assert isinstance(a2kit.App("svc"), a2kit.App)


def test_composition_verbs_chain() -> None:
    """Each composition verb returns the App for chaining."""
    app = a2kit.App("svc")
    assert app.add_router(_Probe()) is app
    assert app.provide(int, lambda: 1) is app


def test_add_router_registers_router_and_tools() -> None:
    app = a2kit.App("p").add_router(_Probe())
    assert len(app.routers()) == 1
    assert len(app.tools()) == 1


def test_add_cli_appends() -> None:
    @click.group()
    def my_group() -> None:
        pass

    app = a2kit.App("p").add_cli(my_group)
    assert app.cli_extras() == [my_group]


def test_add_mcp_middleware_appends() -> None:
    sentinel = object()
    app = a2kit.App("p").add_mcp_middleware(sentinel)
    assert app.mcp_middlewares() == [sentinel]


def test_health_check_installs_meta_router() -> None:
    """Registering a health_check auto-installs the _meta router."""
    app = a2kit.App("svc")

    @app.health_check
    async def _probe() -> a2kit.HealthResult:
        return a2kit.HealthResult.ok()

    assert any(r.slug == "_meta" for r in app.routers())


# ----------------------- no public AppBuilder / build ---------------------- #


def test_appbuilder_is_not_a_public_symbol() -> None:
    """`from a2kit import AppBuilder` fails — there is one type, App."""
    with pytest.raises(ImportError):
        from a2kit import AppBuilder  # noqa: F401


def test_app_has_no_public_build() -> None:
    """The App carries no public `build()` — finishers seal internally."""
    assert not hasattr(a2kit.App("svc"), "build")


# -------------------------------- sealing ---------------------------------- #


def test_seal_validates_provider_graph() -> None:
    """Sealing rejects an app-scope factory that depends on a per-call type."""
    app = a2kit.App("svc")
    app.provide(_PerCall, per_call=True)
    app.provide(_AppScopeNeedsPerCall)
    with pytest.raises(TypeError, match="scope violation"):
        app._seal()


def test_seal_is_idempotent_app_reusable() -> None:
    """A second seal is a no-op — one App survives more than one finisher."""
    app = a2kit.App("svc")
    app._seal()
    app._seal()  # no "spent" / "already sealed" error


@pytest.mark.parametrize(
    "verb",
    ["add_router", "add_cli", "add_mcp_middleware", "provide", "health_check"],
)
def test_composition_after_sealing_raises(verb: str) -> None:
    """A composition verb on a sealed App raises a TypeError sealed-hint."""
    app = a2kit.App("svc")
    app._seal()
    with pytest.raises(TypeError, match="sealed"):
        getattr(app, verb)(_Probe())


def test_finisher_seals_then_composition_raises() -> None:
    """After a real finisher (testing.client) seals, provide raises."""
    from a2kit.testing import client

    app = a2kit.App("svc").add_router(_Probe())

    async def go() -> None:
        async with client(app):
            pass

    asyncio.run(go())
    with pytest.raises(TypeError, match="sealed"):
        app.provide(int, lambda: 1)


# ---------------------------- runtime surface ------------------------------ #


def test_app_unknown_attr_is_attributeerror() -> None:
    """Unknown attribute access stays AttributeError so getattr/hasattr behave."""
    app = a2kit.App("p")
    assert not hasattr(app, "use")
    assert not hasattr(app, "connect")
    assert getattr(app, "version", "DEFAULT") == "DEFAULT"


def test_app_is_an_async_context_manager() -> None:
    """The App enters/exits its own lifecycle."""
    app = a2kit.App("p").add_router(_Probe())

    async def go() -> None:
        async with app as entered:
            assert entered is app

    asyncio.run(go())


# ----------------------- test overrides are re-build ----------------------- #


def test_reregistered_provider_wins_last_write() -> None:
    """provide() is last-write-wins — the override mechanism (ADR 0006)."""

    class _Service:
        def __init__(self, tag: str = "real") -> None:
            self.tag = tag

    app = a2kit.App("svc")
    app.provide(_Service, lambda: _Service("real"))
    app.provide(_Service, lambda: _Service("fake"))
    resolved = asyncio.run(app.container().get(_Service))
    assert resolved.tag == "fake"


def test_no_post_seal_override_surface_on_container() -> None:
    """The snapshot/restore test-override seam was deleted (ADR 0006)."""
    container = a2kit.App("svc").container()
    for removed in ("_override", "_snapshot", "_restore"):
        assert not hasattr(container, removed)


# --------------------------- LDD kill-switch ------------------------------- #


def test_ldd_defaults_enabled() -> None:
    app = a2kit.App("p")
    assert app.ldd_reports is True
    assert app.ldd_events is True


def test_set_ldd_disables_reports() -> None:
    app = a2kit.App("p").set_ldd(reports=False)
    assert app.ldd_reports is False
    assert app.ldd_events is True


def test_set_ldd_disables_events() -> None:
    app = a2kit.App("p").set_ldd(events=False)
    assert app.ldd_events is False
    assert app.ldd_reports is True


def test_set_ldd_chainable() -> None:
    app = a2kit.App("p")
    assert app.set_ldd(reports=False) is app


def test_set_ldd_none_keeps_existing() -> None:
    app = a2kit.App("p").set_ldd(reports=False, events=False)
    app.set_ldd(reports=True)  # only flips reports
    assert app.ldd_reports is True
    assert app.ldd_events is False


def test_env_var_off_disables_both(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("A2KIT_LDD", "off")
    app = a2kit.App("p")
    assert app.ldd_reports is False
    assert app.ldd_events is False


def test_env_var_unset_default_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("A2KIT_LDD", raising=False)
    app = a2kit.App("p")
    assert app.ldd_reports is True
    assert app.ldd_events is True
