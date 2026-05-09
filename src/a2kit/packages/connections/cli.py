"""Connection-management CLI as a factory.

``connections_cli(TrackerConn, OtherConn)`` returns a Click group with
``login``/``logout``/``list``/``show``/``delete`` subcommands bound to
the passed connection types. Wire via ``app.add_cli(connections_cli(...))``.
"""

from __future__ import annotations

import asyncio
import tomllib
from typing import Any

import click

from a2kit.packages.connections.config import ConnectionConfig, default_config_dir
from a2kit.packages.connections.exceptions import ConnectionNotFound
from a2kit.packages.connections.store import ConnectionStore


def _parse_field_overrides(field_pairs: tuple[str, ...]) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in field_pairs:
        if "=" not in raw:
            msg = f"--field expects KEY=VALUE, got {raw!r}"
            raise click.BadParameter(msg)
        k, v = raw.split("=", 1)
        out[k.strip()] = v
    return out


def _parse_key_arg(model: type[ConnectionConfig], key_arg: str | None) -> tuple[str, ...]:
    fields = model._key_field_names()
    if key_arg is None:
        msg = "--key required (e.g. --key='project,env,db' or --key=name for single-field)"
        raise click.BadParameter(msg)
    parts = tuple(p.strip() for p in key_arg.split(",")) if "," in key_arg else (key_arg.strip(),)
    if len(parts) != len(fields):
        msg = f"--key arity mismatch: expected {fields}, got {parts}"
        raise click.BadParameter(msg)
    return parts


def _mask_secret_fields(_model: type[ConnectionConfig], data: dict[str, Any]) -> dict[str, Any]:
    secret_hints = ("secret", "token", "password", "api_key", "apikey")
    out = dict(data)
    for k in list(out):
        if any(h in k.lower() for h in secret_hints) and isinstance(out[k], str):
            out[k] = "***"
    return out


def _build_registry(conn_types: tuple[type[ConnectionConfig], ...]) -> dict[str, type[ConnectionConfig]]:
    out: dict[str, type[ConnectionConfig]] = {}
    for ct in conn_types:
        out[ct.__name__] = ct
        out[ct.__name__.lower()] = ct
    return out


def connections_cli(*conn_types: type[ConnectionConfig]) -> click.Group:
    """Return a ``connections`` Click group bound to the given connection types."""
    registry = _build_registry(conn_types)

    @click.group(name="connections")
    def group() -> None:
        """Manage saved connection records."""

    def _resolve(conn_type: str) -> type[ConnectionConfig]:
        model = registry.get(conn_type)
        if model is None:
            click.echo(
                f"Unknown connection type {conn_type!r}. Registered: {sorted(set(registry))}",
                err=True,
            )
            raise click.exceptions.Exit(1)
        return model

    @group.command(name="login")
    @click.argument("conn_type")
    @click.option("--key", "key_arg", default=None, help="Comma-separated key parts.")
    @click.option("--field", "fields", multiple=True, help="KEY=VALUE field; repeat for each.")
    def login_cmd(conn_type: str, key_arg: str | None, fields: tuple[str, ...]) -> None:
        """Save a connection TOML."""
        model = _resolve(conn_type)
        key = _parse_key_arg(model, key_arg)
        overrides = _parse_field_overrides(fields)
        info = model(key=key, **overrides)
        store = ConnectionStore(model)
        path = asyncio.run(store.save(info))
        click.echo(f"saved: {path}")

    @group.command(name="delete")
    @click.argument("conn_type")
    @click.option("--key", "key_arg", default=None)
    def delete_cmd(conn_type: str, key_arg: str | None) -> None:
        """Delete a connection TOML."""
        _delete(conn_type, key_arg)

    @group.command(name="logout")
    @click.argument("conn_type")
    @click.option("--key", "key_arg", default=None)
    def logout_cmd(conn_type: str, key_arg: str | None) -> None:
        """Alias for delete."""
        _delete(conn_type, key_arg)

    def _delete(conn_type: str, key_arg: str | None) -> None:
        model = _resolve(conn_type)
        key = _parse_key_arg(model, key_arg)
        store = ConnectionStore(model)
        try:
            asyncio.run(store.delete(key))
        except ConnectionNotFound as exc:
            click.echo(str(exc), err=True)
            raise click.exceptions.Exit(1) from exc
        click.echo(f"deleted: {'-'.join(key)}")

    @group.command(name="list")
    @click.argument("conn_type", required=False)
    def list_cmd(conn_type: str | None) -> None:
        """List saved connections (all registered types if no conn_type)."""
        if conn_type:
            model = _resolve(conn_type)
            store = ConnectionStore(model)
            for info in asyncio.run(store.list_connections()):
                click.echo(f"{conn_type}\t{'-'.join(info.key)}")
            return
        if registry:
            for name in sorted({m.__name__ for m in registry.values()}):
                model = next(m for m in registry.values() if m.__name__ == name)
                store = ConnectionStore(model)
                for info in asyncio.run(store.list_connections()):
                    click.echo(f"{name}\t{'-'.join(info.key)}")
            return
        cfg_dir = default_config_dir()
        if not cfg_dir.exists():
            return
        for path in sorted(cfg_dir.glob("*.toml")):
            click.echo(path.stem)

    @group.command(name="show")
    @click.argument("conn_type")
    @click.option("--key", "key_arg", default=None)
    def show_cmd(conn_type: str, key_arg: str | None) -> None:
        """Print TOML contents (secret-marked fields masked)."""
        model = _resolve(conn_type)
        key = _parse_key_arg(model, key_arg)
        store = ConnectionStore(model)
        path = store._path(key)
        if not path.exists():
            click.echo(str(ConnectionNotFound(key)), err=True)
            raise click.exceptions.Exit(1)
        data = tomllib.loads(path.read_text())
        masked = _mask_secret_fields(model, data)
        for k, v in masked.items():
            click.echo(f"{k} = {v!r}")

    return group


__all__ = ["connections_cli"]
