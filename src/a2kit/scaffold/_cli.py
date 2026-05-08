"""Click-based CLI scaffolding + ephemeral-connection argv parsing.

`build_cli(store)` returns a Click group with login/logout/connections
commands. `register_ephemeral_connections` and `_parse_multistore_register`
parse `--register key=val` argv blocks for the runner.

v0.12: per-block parsing factored into `RegisterBlock` (a `click.ParamType`)
so it's reusable from plugins or any Click-based CLI. The argv walkers now
just find `--register` runs and delegate each block's parsing to
`RegisterBlock.convert()`.
"""

from __future__ import annotations

from typing import Any, TypeVar

import click

from a2kit.connections import ConnectionInfo, ConnectionStore
from a2kit.exceptions import ConnectionNotFound

C = TypeVar("C", bound=ConnectionInfo)


def _parse_kv_pair(item: str) -> tuple[str, str]:
    if "=" not in item:
        msg = f"Expected key=value, got {item!r}"
        raise click.BadParameter(msg)
    k, v = item.split("=", 1)
    return k.strip(), v.strip()


def _parse_key_arg(raw: str) -> tuple[str, ...]:
    """Parse a connection key from a CLI string. Accepts `a/b/c` or single name."""
    if "/" in raw:
        return tuple(p for p in raw.split("/") if p)
    return (raw,)


class RegisterBlock(click.ParamType):
    """Click `ParamType` parsing one `--register` block.

    Accepts either:
    - `"router:key field1=val field2=val"` (whitespace-separated, one quoted arg)
    - A pre-tokenised list: `["router:key", "field1=val", "field2=val"]`

    Returns a 3-tuple ``(router_name | None, key_tuple, kwargs)``. The runner
    resolves `router_name` against its store registry; ``None`` means "use the
    fallback single store".

    Used both as a `click.ParamType` (for Click-based CLIs that take
    `--register "block"` as one option) and as a per-block parser called by
    the legacy multi-arg argv walkers.
    """

    name = "register"

    def convert(self, value: Any, param: Any = None, ctx: Any = None) -> tuple[str | None, tuple[str, ...], dict[str, str]]:
        import shlex  # noqa: PLC0415

        tokens: list[str]
        if isinstance(value, str):
            tokens = shlex.split(value)
        elif isinstance(value, (list, tuple)):
            tokens = [str(t) for t in value]
        else:  # pragma: no cover — Click only supplies str
            self.fail(f"--register expected a string or list, got {type(value).__name__}", param, ctx)

        if not tokens:
            self.fail("--register requires a key argument", param, ctx)

        head, *kvs = tokens
        if ":" in head:
            router, key_part = head.split(":", 1)
        else:
            router, key_part = None, head
        kwargs: dict[str, str] = {}
        for kv in kvs:
            if "=" not in kv:
                # Defensive: malformed input. Skip silently — matches v0.11
                # multi-arg walker behaviour where non-`=` tokens stopped the
                # block and were treated as a new positional.
                break
            k, v = _parse_kv_pair(kv)
            kwargs[k] = v
        return router, _parse_key_arg(key_part), kwargs


def _walk_register_args(args: list[str]) -> list[list[str]]:
    """Split a flat argv list into per-`--register` blocks.

    Each block is the tokens between one `--register` and the next (or end).
    Empty `--register` (no following key) raises `ValueError`.
    """
    blocks: list[list[str]] = []
    i = 0
    while i < len(args):
        if args[i] != "--register":
            i += 1
            continue
        if i + 1 >= len(args):
            msg = "--register requires a key argument"
            raise ValueError(msg)
        block: list[str] = [args[i + 1]]
        j = i + 2
        while j < len(args) and args[j] != "--register":
            if "=" in args[j]:
                block.append(args[j])
                j += 1
            else:
                break
        blocks.append(block)
        i = j
    return blocks


def _attach_login_command(cli: click.Group, store: ConnectionStore[C], anyio_mod: Any) -> None:
    connection_class = store.connection_class

    @cli.command("login")
    @click.argument("key")
    @click.option("--field", "fields", multiple=True, help="Field assignment as key=value. Repeat per field.")
    def login(key: str, fields: tuple[str, ...]) -> None:
        """Save a connection. KEY is `a/b/c` for tuple keys or `name` for single-part."""
        key_tuple = _parse_key_arg(key)
        kwargs: dict[str, Any] = {}
        for item in fields:
            k, v = _parse_kv_pair(item)
            kwargs[k] = v
        info = connection_class(key=key_tuple, **kwargs)
        path = anyio_mod.run(store.save, info)
        click.echo(f"Saved: {path}")


def _attach_logout_command(cli: click.Group, store: ConnectionStore[C], anyio_mod: Any) -> None:
    @cli.command("logout")
    @click.argument("key")
    def logout(key: str) -> None:
        """Remove a saved connection."""
        try:
            anyio_mod.run(store.delete, _parse_key_arg(key))
        except ConnectionNotFound as exc:
            raise click.ClickException(str(exc)) from exc
        click.echo(f"Removed: {key}")


def _attach_connections_group(cli: click.Group, store: ConnectionStore[C], anyio_mod: Any) -> None:
    @cli.group("connections")
    def connections() -> None:
        """Manage saved connections."""

    @connections.command("list")
    def connections_list() -> None:
        """List all saved connections."""
        results = anyio_mod.run(store.list_connections)
        if not results:
            click.echo("No connections found.")
            return
        for info in results:
            click.echo("/".join(info.key))

    @connections.command("show")
    @click.argument("key")
    def connections_show(key: str) -> None:
        """Show one saved connection (no secrets resolved)."""
        try:
            info = anyio_mod.run(store.load, _parse_key_arg(key))
        except ConnectionNotFound as exc:
            raise click.ClickException(str(exc)) from exc
        click.echo(info.model_dump_json(indent=2))

    @connections.command("delete")
    @click.argument("key")
    def connections_delete(key: str) -> None:
        """Delete a saved connection."""
        try:
            anyio_mod.run(store.delete, _parse_key_arg(key))
        except ConnectionNotFound as exc:
            raise click.ClickException(str(exc)) from exc
        click.echo(f"Removed: {key}")


def build_cli(
    store: ConnectionStore[C],
    *,
    name: str = "a2kit",
) -> click.Group:
    """Build a Click group with standard connection-management commands.

    v0.11: store methods are async; Click is sync. Each command wraps the
    one async call site with `anyio.run(...)` — the rest of the command body
    stays sync.
    """
    import anyio  # noqa: PLC0415

    @click.group(name=name, invoke_without_command=True)
    @click.pass_context
    def cli(ctx: click.Context) -> None:
        if ctx.invoked_subcommand is None:
            click.echo(ctx.get_help())

    _attach_login_command(cli, store, anyio)
    _attach_logout_command(cli, store, anyio)
    _attach_connections_group(cli, store, anyio)
    return cli


def register_ephemeral_connections(
    args: list[str],
    *,
    store: ConnectionStore[C],
) -> dict[tuple[str, ...], C]:
    """Parse `--register` blocks from a flat argv list against a single store."""
    parser = RegisterBlock()
    connection_class = store.connection_class
    out: dict[tuple[str, ...], C] = {}
    for block in _walk_register_args(args):
        _router, key_tuple, kwargs = parser.convert(block)
        info = connection_class(key=key_tuple, **kwargs)
        out[info.key] = info
    return out


def _parse_multistore_register(
    args: list[str],
    stores_by_router: dict[str, Any],
) -> dict[tuple[str, ...], Any]:
    """Parse `--register router:key=...` for multi-store MCPs.

    Bare `--register key=...` (no `router:` prefix) raises a clear error
    listing the available router prefixes.
    """
    parser = RegisterBlock()
    out: dict[tuple[str, ...], Any] = {}
    for block in _walk_register_args(args):
        router_name, key_tuple, kwargs = parser.convert(block)
        if router_name is None:
            raw_key = block[0]
            msg = (
                f"--register {raw_key!r}: ambiguous in a multi-store MCP. "
                f"Use `router:key` form. Available routers: {sorted(stores_by_router)}."
            )
            raise ValueError(msg)
        if router_name not in stores_by_router:
            raw_key = block[0]
            msg = f"--register {raw_key!r}: unknown router prefix {router_name!r}. Available: {sorted(stores_by_router)}."
            raise ValueError(msg)
        store = stores_by_router[router_name]
        info = store.connection_class(key=key_tuple, **kwargs)
        out[info.key] = info
    return out


__all__ = [
    "RegisterBlock",
    "_parse_key_arg",
    "_parse_kv_pair",
    "_parse_multistore_register",
    "build_cli",
    "register_ephemeral_connections",
]
