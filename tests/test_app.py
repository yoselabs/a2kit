from __future__ import annotations

import click
import pytest

import a2kit


class _Probe(a2kit.Router):
    slug = "_probe"
    @a2kit.read("get")
    async def get(self, *, connection: str = "default") -> dict:
        return {"connection": connection}
    tools = (get,)


def test_add_router_appends() -> None:
    app = a2kit.App("p").add_router(_Probe())
    assert len(app.routers()) == 1
    assert len(app.tools()) == 1


def test_add_router_chainable() -> None:
    app = a2kit.App("p")
    out = app.add_router(_Probe())
    assert out is app


def test_add_cli_appends() -> None:
    @click.group()
    def my_group() -> None:
        pass

    app = a2kit.App("p").add_cli(my_group)
    assert app._cli_extras == [my_group]


def test_add_mcp_middleware_appends() -> None:
    sentinel = object()
    app = a2kit.App("p").add_mcp_middleware(sentinel)
    assert app._mcp_middlewares == [sentinel]


def test_app_has_no_use_method() -> None:
    app = a2kit.App("p")
    with pytest.raises(AttributeError):
        app.use(_Probe())  # type: ignore[attr-defined]


def test_app_has_no_connect_method() -> None:
    app = a2kit.App("p")
    assert not hasattr(app, "connect")


def test_app_has_no_use_factory_method() -> None:
    app = a2kit.App("p")
    assert not hasattr(app, "use_factory")


def test_app_has_no_plugins_registry() -> None:
    app = a2kit.App("p")
    assert not hasattr(app, "_plugins")
    assert not hasattr(app, "plugins")


# --- LDD kill-switch --- #


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
    out = app.set_ldd(reports=False)
    assert out is app


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
