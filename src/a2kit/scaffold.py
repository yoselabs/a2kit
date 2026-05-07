"""CLI/MCP entrypoint scaffolding helpers.

Provides building blocks — NOT a `main()`. The MCP author owns the FastMCP server
instance and the program entry; a2kit only ships the recurring chunks.

Three helpers:

- `build_cli(store, connection_class)` — returns a `click.Group` with the standard
  `login`/`logout`/`connections list`/`connections show`/`connections delete`
  commands wired against the store. The author adds their own commands (typically
  `serve`) via `cli.add_command(...)`.
- `register_ephemeral_connections(args, connection_class)` — parses
  `--register key=val key=val` style args into in-memory connections, returning a
  dict keyed by the connection key tuple. The author wires this into their MCP
  argparse/click as appropriate.
- `scope_filter(store, scope)` — read-only filtered view of a store, useful for
  the a2atlassian-style `--scope` flag.

Why no `main()`? Both reference MCPs differ on what their `main()` does
(`--enable jira`, `--scope`, `--register`, etc.). Forcing a shape would push
either too much or too little into a2kit. Keep it composable.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any, ClassVar, Generic, TypeVar

import click

from a2kit.connections import ConnectionInfo, ConnectionStore
from a2kit.exceptions import ConnectionNotFound

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

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


def build_cli(  # noqa: C901
    store: ConnectionStore[C],
    *,
    connection_class: type[C] | None = None,
    name: str = "a2kit",
) -> click.Group:
    """Build a Click group with standard connection-management commands.

    v0.3: `connection_class` is derived from `store.connection_class`. Passing it
    explicitly emits a `DeprecationWarning` for one cycle. Going forward the
    walkthrough is just `build_cli(store, name="...")`.
    """
    if connection_class is not None:
        import warnings  # noqa: PLC0415

        warnings.warn(
            "build_cli(connection_class=...) is deprecated; the store knows its model. "
            "Drop the kwarg — `build_cli(store, name=...)` is enough.",
            DeprecationWarning,
            stacklevel=2,
        )
    connection_class = connection_class or store.connection_class

    @click.group(name=name, invoke_without_command=True)
    @click.pass_context
    def cli(ctx: click.Context) -> None:
        if ctx.invoked_subcommand is None:
            click.echo(ctx.get_help())

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
        path = store.save(info)
        click.echo(f"Saved: {path}")

    @cli.command("logout")
    @click.argument("key")
    def logout(key: str) -> None:
        """Remove a saved connection."""
        try:
            store.delete(_parse_key_arg(key))
        except ConnectionNotFound as exc:
            raise click.ClickException(str(exc)) from exc
        click.echo(f"Removed: {key}")

    @cli.group("connections")
    def connections() -> None:
        """Manage saved connections."""

    @connections.command("list")
    def connections_list() -> None:
        """List all saved connections."""
        results = store.list_connections()
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
            info = store.load(_parse_key_arg(key))
        except ConnectionNotFound as exc:
            raise click.ClickException(str(exc)) from exc
        click.echo(info.model_dump_json(indent=2))

    @connections.command("delete")
    @click.argument("key")
    def connections_delete(key: str) -> None:
        """Delete a saved connection."""
        try:
            store.delete(_parse_key_arg(key))
        except ConnectionNotFound as exc:
            raise click.ClickException(str(exc)) from exc
        click.echo(f"Removed: {key}")

    return cli


def register_ephemeral_connections(
    args: list[str],
    connection_class: type[C] | None = None,
    *,
    store: ConnectionStore[C] | None = None,
) -> dict[tuple[str, ...], C]:
    """Parse `--register` blocks from a flat argv list.

    v0.3: prefer `register_ephemeral_connections(args, store=store)` — the store
    knows its model. Passing `connection_class` positionally still works for one
    cycle but emits a `DeprecationWarning`.
    """
    if connection_class is None and store is None:
        msg = "register_ephemeral_connections requires either store= or connection_class"
        raise TypeError(msg)
    if connection_class is not None and store is None:
        import warnings  # noqa: PLC0415

        warnings.warn(
            "Pass `store=` instead of `connection_class=`; the store knows its model.",
            DeprecationWarning,
            stacklevel=2,
        )
    if store is not None:
        connection_class = store.connection_class
    assert connection_class is not None  # for type narrowing  # noqa: S101
    out: dict[tuple[str, ...], C] = {}
    i = 0
    while i < len(args):
        if args[i] != "--register":
            i += 1
            continue
        if i + 1 >= len(args):
            msg = "--register requires a key argument"
            raise ValueError(msg)
        key_tuple = _parse_key_arg(args[i + 1])
        kwargs: dict[str, Any] = {}
        j = i + 2
        while j < len(args) and args[j] != "--register":
            if "=" in args[j]:
                k, v = _parse_kv_pair(args[j])
                kwargs[k] = v
                j += 1
            else:
                # not a kv pair and not --register: stop collecting (caller's flag)
                break
        info = connection_class(key=key_tuple, **kwargs)
        out[info.key] = info
        i = j
    return out


class _FilteredStore(Generic[C]):
    """Read-only view of a `ConnectionStore` restricted to a key-substring scope."""

    def __init__(self, store: ConnectionStore[C], scope: str) -> None:
        self._store = store
        self._scope = scope

    def _matches(self, key: tuple[str, ...]) -> bool:
        return any(self._scope == part for part in key)

    def load(self, key: tuple[str, ...]) -> C:
        if not self._matches(key):
            raise ConnectionNotFound(key)
        return self._store.load(key)

    def list_connections(self) -> list[C]:
        return [info for info in self._store.list_connections() if self._matches(info.key)]

    @property
    def config_dir(self) -> Any:
        return self._store.config_dir


def scope_filter(store: ConnectionStore[C], scope: str | None) -> Any:
    """Return a read-only filtered view of `store`.

    If `scope` is `None`, the original store is returned unchanged. Otherwise a
    proxy is returned that exposes `load`/`list_connections`/`config_dir` and
    raises `ConnectionNotFound` for any key not containing `scope` as a part.

    This generalises a2atlassian's `--scope` flag (`mcp_server.py:50-53`). It
    intentionally returns a read-only proxy — scoping write paths is the
    consumer's call.
    """
    if scope is None:
        return store
    return _FilteredStore(store, scope)


__all__ = [
    "Feature",
    "FeatureRegistry",
    "MCPRunner",
    "build_cli",
    "register_ephemeral_connections",
    "scope_filter",
]


# --------------------------------------------------------------------------- #
# FeatureRegistry — feature-module registration with `--enable`.
#
# Generalises a2atlassian's `FEATURES = {...}` + `_register_jira_tools` /
# `_register_confluence_tools` pattern (`mcp_server.py:144-176`). Each feature
# class defines `register_read(server, store)` and optionally
# `register_write(server, store)`. The registry tracks (name, default,
# feature_obj) triples; `apply()` filters by `enabled` set and includes writes
# iff `include_writes`.
# --------------------------------------------------------------------------- #


class Feature:
    """Base class for v0.3 feature modules.

    Bundles enricher + snapshot_dir + cassette_dir + register hooks. Subclass and
    register an instance with a `FeatureRegistry`. The legacy v0.2 decorator
    path (`@registry.feature("name", default=True)`) still works and is now a
    thin wrapper around an anonymous `Feature` subclass.
    """

    name: ClassVar[str] = ""
    default: ClassVar[bool] = False
    enricher: ClassVar[Any] = None
    snapshot_dir: ClassVar[Path | str | None] = None
    cassette_dir: ClassVar[Path | str | None] = None
    requires_writes: ClassVar[bool] = False

    def register_read(self, server: Any, store: Any) -> None:
        """Register read-only tools. Override in subclasses."""

    def register_write(self, server: Any, store: Any) -> None:
        """Register write-marked tools. Override in subclasses."""


class FeatureRegistry:
    """Registry of feature modules — both v0.2 decorator-style and v0.3 `Feature` instances.

    v0.3: prefer `registry.add(IssuesFeature())`. The `@registry.feature(...)`
    decorator stays for backward compat with v0.2 examples.
    """

    def __init__(self) -> None:
        self._features: list[tuple[str, bool, Any]] = []

    def add(self, feature: Feature) -> Feature:
        """Register a `Feature` instance. Returns the instance for chaining."""
        if not feature.name:
            msg = f"{type(feature).__name__}.name must be a non-empty string"
            raise ValueError(msg)
        self._features.append((feature.name, feature.default, feature))
        return feature

    def feature(self, name: str, *, default: bool = False) -> Any:
        """Register a feature class (decorator). v0.2-style; still supported."""

        def decorator(cls: Any) -> Any:
            self._features.append((name, default, cls))
            return cls

        return decorator

    def feature_names(self) -> list[str]:
        """Return ordered feature names."""
        return [name for name, _default, _cls in self._features]

    def defaults(self) -> set[str]:
        """Return the set of names enabled-by-default."""
        return {name for name, default, _cls in self._features if default}

    def apply(
        self,
        server: Any,
        store: Any,
        *,
        enabled: Iterable[str] | None = None,
        include_writes: bool = False,
    ) -> list[str]:
        """Register read tools (always) and write tools (if `include_writes`)."""
        wanted = set(enabled) if enabled is not None else self.defaults()
        unknown = wanted - {name for name, _default, _cls in self._features}
        if unknown:
            msg = f"Unknown feature(s): {sorted(unknown)}; available: {self.feature_names()}"
            raise ValueError(msg)
        applied: list[str] = []
        for name, _default, cls in self._features:
            if name not in wanted:
                continue
            if hasattr(cls, "register_read"):
                cls.register_read(server, store)
            if include_writes and hasattr(cls, "register_write"):
                cls.register_write(server, store)
            applied.append(name)
        return applied


# --------------------------------------------------------------------------- #
# MCPRunner — flag parsing + transport selection.
# --------------------------------------------------------------------------- #


class MCPRunner:
    """Wraps `server.run()` to handle `--register`, `--scope`, `--enable`, `--http`.

    Skip this entirely if you want — calling `server.run()` directly is fully
    supported. The runner only exists to absorb argv-parsing + transport-flag
    boilerplate that both reference MCPs ship by hand.

    Parsed flags:

    - `--register KEY field=val ...` — repeatable; ephemeral connections (no disk write).
    - `--scope <prefix>` — substring filter on the store (read-only proxy).
    - `--enable feat1,feat2` — enable specific feature modules. Comma- or
      space-separated. `--no-enable feat3` removes a default-on feature.
    - `--writes` — include write-marked tool registration (default OFF).
    - `--http [host:port]` — switch transport to streamable HTTP. Default
      `host:port` taken from `server.settings`.

    Transport seam: before `server.run()` is called, the runner sets the
    thread-local in `a2kit.tools` so `@a2kit.tool(streaming=True)` decorators
    can detect stdio vs http.
    """

    def __init__(
        self,
        server: Any,
        *,
        store: Any | None = None,
        feature_registry: FeatureRegistry | None = None,
        connection_class: type[ConnectionInfo] | None = None,
        name: str = "a2kit",
    ) -> None:
        if connection_class is not None:
            import warnings  # noqa: PLC0415

            warnings.warn(
                "MCPRunner(connection_class=...) is deprecated; pass `store=` instead. The store knows its model.",
                DeprecationWarning,
                stacklevel=2,
            )
        self.server = server
        self.store = store
        self.feature_registry = feature_registry
        # Derive from store when present.
        if connection_class is None and store is not None:
            connection_class = store.connection_class
        self.connection_class = connection_class
        self.name = name

    def _parse(self, argv: list[str]) -> dict[str, Any]:
        i = 0
        result: dict[str, Any] = {
            "scope": None,
            "enable": None,
            "no_enable": set(),
            "writes": False,
            "http": None,
            "register_args": [],
        }
        while i < len(argv):
            a = argv[i]
            if a == "--scope" and i + 1 < len(argv):
                result["scope"] = argv[i + 1]
                i += 2
            elif a == "--enable" and i + 1 < len(argv):
                names = [n.strip() for n in argv[i + 1].replace(",", " ").split() if n.strip()]
                result["enable"] = (result["enable"] or []) + names
                i += 2
            elif a == "--no-enable" and i + 1 < len(argv):
                result["no_enable"].update(n.strip() for n in argv[i + 1].split(",") if n.strip())
                i += 2
            elif a == "--writes":
                result["writes"] = True
                i += 1
            elif a == "--http":
                # next token may be host:port or another flag
                if i + 1 < len(argv) and not argv[i + 1].startswith("--"):
                    result["http"] = argv[i + 1]
                    i += 2
                else:
                    result["http"] = ""
                    i += 1
            elif a == "--register":
                # collect this token + the key + a run of `field=value` items until
                # we hit either the next --register, another `--flag`, or the end.
                result["register_args"].append(a)
                i += 1
                while i < len(argv) and not argv[i].startswith("--"):
                    result["register_args"].append(argv[i])
                    i += 1
            else:
                # unknown flag — skip; caller's other parsers can pick it up.
                i += 1
        return result

    def _apply_features(self, parsed: dict[str, Any]) -> None:
        if self.feature_registry is None:
            return
        if parsed["enable"] is None:
            wanted = self.feature_registry.defaults()
        else:
            wanted = set(parsed["enable"])
        wanted -= parsed["no_enable"]
        self.feature_registry.apply(
            self.server,
            self.store,
            enabled=wanted,
            include_writes=parsed["writes"],
        )

    def _ephemeral(self, parsed: dict[str, Any]) -> dict[tuple[str, ...], Any]:
        if self.connection_class is None or not parsed["register_args"]:
            return {}
        return register_ephemeral_connections(parsed["register_args"], self.connection_class)

    def _http_settings(self, raw: str) -> tuple[str, int]:
        host, port = "127.0.0.1", 8080
        if raw:
            if ":" in raw:
                h, p = raw.rsplit(":", 1)
                if h:
                    host = h
                port = int(p)
            else:
                host = raw
        return host, port

    def run(self, argv: list[str] | None = None, *, transport: str | None = None) -> dict[str, Any]:
        """Parse argv, register features, set transport seam, run the server.

        Returns the parsed dict (post-effects) for tests; the server.run() call
        is the side-effect. Pass `transport='stdio'` (or `'http'`) to skip argv
        parsing entirely — useful for inline invocation.
        """
        from a2kit.tools import _set_current_transport  # noqa: PLC0415 — lazy seam

        argv = list(sys.argv[1:]) if argv is None else list(argv)
        parsed = self._parse(argv)
        ephemeral = self._ephemeral(parsed)
        parsed["ephemeral"] = ephemeral
        self._apply_features(parsed)

        chosen = transport
        if chosen is None:
            chosen = "http" if parsed["http"] is not None else "stdio"

        _set_current_transport(chosen)
        try:
            if chosen == "http":
                host, port = self._http_settings(parsed["http"] or "")
                # FastMCP's settings is a Pydantic model — mutate via attr assignment.
                self.server.settings.host = host
                self.server.settings.port = port
                self.server.run(transport="streamable-http")
            else:
                self.server.run(transport="stdio")
        finally:
            _set_current_transport(None)
        return parsed
