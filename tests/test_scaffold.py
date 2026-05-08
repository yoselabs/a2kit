"""Tests for a2kit.scaffold — build_cli, register_ephemeral_connections, scope_filter."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from click.testing import CliRunner

from a2kit import ConnectionNotFound
from a2kit.scaffold import (
    build_cli,
    register_ephemeral_connections,
    scope_filter,
)

if TYPE_CHECKING:
    from a2kit import ConnectionStore

    from .conftest import AtlassianInfo, DbInfo


def test_build_cli_login_logout_show_list_delete(
    atlassian_store: ConnectionStore[AtlassianInfo],
) -> None:

    cli = build_cli(atlassian_store, name="a2x")
    runner = CliRunner()

    # login
    result = runner.invoke(
        cli,
        [
            "login",
            "prod",
            "--field",
            "url=https://x",
            "--field",
            "email=e@x",
            "--field",
            "token=t",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Saved" in result.output

    # connections list
    result = runner.invoke(cli, ["connections", "list"])
    assert result.exit_code == 0
    assert "prod" in result.output

    # connections show
    result = runner.invoke(cli, ["connections", "show", "prod"])
    assert result.exit_code == 0
    assert "https://x" in result.output

    # connections delete
    result = runner.invoke(cli, ["connections", "delete", "prod"])
    assert result.exit_code == 0
    # logout (now missing) — exits with click error
    result = runner.invoke(cli, ["logout", "prod"])
    assert result.exit_code != 0


def test_build_cli_no_subcommand_shows_help(
    atlassian_store: ConnectionStore[AtlassianInfo],
) -> None:

    cli = build_cli(atlassian_store)
    runner = CliRunner()
    result = runner.invoke(cli, [])
    assert result.exit_code == 0
    assert "Usage" in result.output


def test_build_cli_show_missing_raises(
    atlassian_store: ConnectionStore[AtlassianInfo],
) -> None:

    cli = build_cli(atlassian_store)
    runner = CliRunner()
    result = runner.invoke(cli, ["connections", "show", "missing"])
    assert result.exit_code != 0


def test_build_cli_login_invalid_field_format(
    atlassian_store: ConnectionStore[AtlassianInfo],
) -> None:

    cli = build_cli(atlassian_store)
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["login", "prod", "--field", "no-equals-here"],
    )
    assert result.exit_code != 0


def test_build_cli_logout_succeeds_after_login(
    atlassian_store: ConnectionStore[AtlassianInfo],
) -> None:

    cli = build_cli(atlassian_store)
    runner = CliRunner()
    runner.invoke(cli, ["login", "test", "--field", "url=https://x", "--field", "email=e", "--field", "token=t"])
    result = runner.invoke(cli, ["logout", "test"])
    assert result.exit_code == 0
    assert "Removed" in result.output


def test_build_cli_connections_delete_missing_raises(
    atlassian_store: ConnectionStore[AtlassianInfo],
) -> None:

    cli = build_cli(atlassian_store)
    runner = CliRunner()
    result = runner.invoke(cli, ["connections", "delete", "ghost"])
    assert result.exit_code != 0


def test_build_cli_logout_missing_raises(
    atlassian_store: ConnectionStore[AtlassianInfo],
) -> None:

    cli = build_cli(atlassian_store)
    runner = CliRunner()
    result = runner.invoke(cli, ["logout", "ghost"])
    assert result.exit_code != 0


def test_build_cli_list_empty(atlassian_store: ConnectionStore[AtlassianInfo]) -> None:

    cli = build_cli(atlassian_store)
    runner = CliRunner()
    result = runner.invoke(cli, ["connections", "list"])
    assert "No connections" in result.output


def test_build_cli_handles_multipart_keys(db_store: ConnectionStore[DbInfo]) -> None:

    cli = build_cli(db_store)
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["login", "acme/prod/main", "--field", "dsn=postgresql://x"],
    )
    assert result.exit_code == 0
    result = runner.invoke(cli, ["connections", "list"])
    assert "acme/prod/main" in result.output


def test_register_ephemeral_parses_single_block(atlassian_store: ConnectionStore[AtlassianInfo]) -> None:
    out = register_ephemeral_connections(["--register", "prod", "url=https://x", "email=e", "token=t"], store=atlassian_store)
    assert ("prod",) in out


def test_register_ephemeral_parses_multiple_blocks(atlassian_store: ConnectionStore[AtlassianInfo]) -> None:
    out = register_ephemeral_connections(
        [
            "--register",
            "a",
            "url=https://x",
            "email=e",
            "token=t",
            "--register",
            "b",
            "url=https://y",
            "email=e2",
            "token=t2",
        ],
        store=atlassian_store,
    )
    assert {("a",), ("b",)} == set(out.keys())


def test_register_ephemeral_stops_at_unknown_token(atlassian_store: ConnectionStore[AtlassianInfo]) -> None:
    out = register_ephemeral_connections(["--register", "a", "url=https://x", "email=e", "token=t", "--other-flag"], store=atlassian_store)
    assert ("a",) in out


def test_register_ephemeral_skips_non_register_args(atlassian_store: ConnectionStore[AtlassianInfo]) -> None:
    out = register_ephemeral_connections(["--unrelated", "x"], store=atlassian_store)
    assert out == {}


def test_register_ephemeral_missing_key_raises(atlassian_store: ConnectionStore[AtlassianInfo]) -> None:
    with pytest.raises(ValueError, match="key argument"):
        register_ephemeral_connections(["--register"], store=atlassian_store)


def test_register_ephemeral_stops_at_non_kv_arg(db_store: ConnectionStore[DbInfo]) -> None:
    out = register_ephemeral_connections(["--register", "a/b/c", "dsn=postgresql://x", "no-equals"], store=db_store)
    assert ("a", "b", "c") in out


async def test_scope_filter_returns_store_when_none(
    atlassian_store: ConnectionStore[AtlassianInfo],
) -> None:
    out = scope_filter(atlassian_store, None)
    assert out is atlassian_store


async def test_scope_filter_blocks_load_outside_scope(
    atlassian_store: ConnectionStore[AtlassianInfo],
) -> None:
    from .conftest import AtlassianInfo

    await atlassian_store.save(AtlassianInfo(key=("alpha",), url="https://a", email="e", token="t"))
    await atlassian_store.save(AtlassianInfo(key=("beta",), url="https://b", email="e", token="t"))

    view = scope_filter(atlassian_store, "alpha")
    info = await view.load(("alpha",))
    assert info.url == "https://a"
    with pytest.raises(ConnectionNotFound):
        await view.load(("beta",))

    listed = await view.list_connections()
    assert {info.key for info in listed} == {("alpha",)}
    assert view.config_dir == atlassian_store.config_dir
