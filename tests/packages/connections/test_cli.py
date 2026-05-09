"""`connections_cli(...)` round-trip via CliRunner."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from a2kit.packages.connections import connections_cli

from .conftest import WidgetConfig


@pytest.fixture(autouse=True)
def _isolated_config_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("A2KIT_CONFIG_HOME", str(tmp_path / "conn"))


def test_login_then_list_then_show_then_delete() -> None:
    group = connections_cli(WidgetConfig)
    runner = CliRunner()
    r = runner.invoke(
        group,
        ["login", "WidgetConfig", "--key=prod", "--field=token=secret-literal"],
    )
    assert r.exit_code == 0, r.output
    assert "saved:" in r.output

    r = runner.invoke(group, ["list", "WidgetConfig"])
    assert r.exit_code == 0, r.output
    assert "prod" in r.output

    r = runner.invoke(group, ["show", "WidgetConfig", "--key=prod"])
    assert r.exit_code == 0, r.output
    assert "***" in r.output  # token masked
    assert "secret-literal" not in r.output

    r = runner.invoke(group, ["delete", "WidgetConfig", "--key=prod"])
    assert r.exit_code == 0, r.output
    assert "deleted" in r.output

    r = runner.invoke(group, ["delete", "WidgetConfig", "--key=prod"])
    assert r.exit_code == 1


def test_logout_alias() -> None:
    group = connections_cli(WidgetConfig)
    runner = CliRunner()
    runner.invoke(group, ["login", "WidgetConfig", "--key=prod", "--field=token=t"])
    r = runner.invoke(group, ["logout", "WidgetConfig", "--key=prod"])
    assert r.exit_code == 0


def test_unknown_conn_type() -> None:
    group = connections_cli(WidgetConfig)
    runner = CliRunner()
    r = runner.invoke(group, ["login", "Nope", "--key=prod", "--field=token=t"])
    assert r.exit_code == 1
    assert "Unknown connection type" in r.output


def test_list_no_conn_types_falls_back_to_filenames(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_home = tmp_path / "conn-fallback"
    cfg_home.mkdir()
    (cfg_home / "alpha.toml").write_text('key = ["alpha"]\ntoken = "t"\nurl = ""\n')
    monkeypatch.setenv("A2KIT_CONFIG_HOME", str(cfg_home))
    group = connections_cli()  # no conn types — fallback path
    runner = CliRunner()
    r = runner.invoke(group, ["list"])
    assert r.exit_code == 0
    assert "alpha" in r.output
