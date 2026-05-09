"""Click `connections` subgroup round-trip via CliRunner."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from a2kit.packages.connections.cli import connections_group
from .conftest import WidgetConfig


@pytest.fixture(autouse=True)
def _isolated_config_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("A2KIT_CONFIG_HOME", str(tmp_path / "conn"))


@pytest.fixture
def app_with_widget(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    """Inject an App with WidgetConfig registered into the connections.cli ContextVar shim."""
    import a2kit.packages.connections.cli as cli_mod
    from a2kit.app import App

    app = App("test")
    app.connect(WidgetConfig)
    monkeypatch.setattr(cli_mod, "_get_app", lambda: app)
    return app


def test_login_then_list_then_show_then_delete(
    app_with_widget,  # type: ignore[no-untyped-def]
) -> None:
    runner = CliRunner()
    r = runner.invoke(
        connections_group,
        ["login", "WidgetConfig", "--key=prod", "--field=token=secret-literal"],
    )
    assert r.exit_code == 0, r.output
    assert "saved:" in r.output

    r = runner.invoke(connections_group, ["list", "WidgetConfig"])
    assert r.exit_code == 0, r.output
    assert "prod" in r.output

    r = runner.invoke(connections_group, ["show", "WidgetConfig", "--key=prod"])
    assert r.exit_code == 0, r.output
    assert "***" in r.output  # token masked
    assert "secret-literal" not in r.output

    r = runner.invoke(connections_group, ["delete", "WidgetConfig", "--key=prod"])
    assert r.exit_code == 0, r.output
    assert "deleted" in r.output

    r = runner.invoke(connections_group, ["delete", "WidgetConfig", "--key=prod"])
    assert r.exit_code == 1


def test_logout_alias(app_with_widget) -> None:  # type: ignore[no-untyped-def]
    runner = CliRunner()
    runner.invoke(
        connections_group,
        ["login", "WidgetConfig", "--key=prod", "--field=token=t"],
    )
    r = runner.invoke(connections_group, ["logout", "WidgetConfig", "--key=prod"])
    assert r.exit_code == 0


def test_unknown_conn_type(app_with_widget) -> None:  # type: ignore[no-untyped-def]
    runner = CliRunner()
    r = runner.invoke(connections_group, ["login", "Nope", "--key=prod", "--field=token=t"])
    assert r.exit_code == 1
    assert "Unknown connection type" in r.output


def test_list_no_app_falls_back_to_filenames(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import a2kit.packages.connections.cli as cli_mod

    cfg_home = tmp_path / "conn-fallback"
    cfg_home.mkdir()
    (cfg_home / "alpha.toml").write_text('key = ["alpha"]\ntoken = "t"\nurl = ""\n')
    monkeypatch.setenv("A2KIT_CONFIG_HOME", str(cfg_home))
    monkeypatch.setattr(cli_mod, "_get_app", lambda: None)
    runner = CliRunner()
    r = runner.invoke(connections_group, ["list"])
    assert r.exit_code == 0
    assert "alpha" in r.output
