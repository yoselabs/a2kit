"""CLI/MCP entrypoint scaffolding helpers.

Provides building blocks — NOT a `main()`. The MCP author owns the FastMCP server
instance and the program entry; a2kit only ships the recurring chunks.

v0.3.1: `Feature` is renamed `Router` (Pydantic BaseModel, Generic over ConnT).
`FeatureRegistry` is renamed `RouterRegistry`. The v0.3 names remain as
`DeprecationWarning` aliases for one cycle.

The runner replaces the v0.3 `--enable`/`--no-enable`/`--writes` flag soup with
a single `--select` flag carrying a boolean expression. v0.3 flags are still
parsed and translated to a `--select` expression internally (with a warning).
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path  # noqa: TC003 — runtime-needed for Pydantic field annotation
from typing import TYPE_CHECKING, Any, Generic, TypeVar

import click
from pydantic import BaseModel, ConfigDict, Field

from a2kit._capabilities import Capability  # noqa: TC001 — runtime-needed for Pydantic field annotation
from a2kit._router_state import _set_active
from a2kit._select import (
    SelectExpr,
    default_select_expr,
    parse_select,
    validate_atoms,
)
from a2kit.connections import ConnectionInfo, ConnectionStore
from a2kit.exceptions import ConnectionNotFound

if TYPE_CHECKING:
    from collections.abc import Iterable

C = TypeVar("C", bound=ConnectionInfo)
ConnT = TypeVar("ConnT", bound=ConnectionInfo)


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
    """Build a Click group with standard connection-management commands."""
    if connection_class is not None:
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
    """Parse `--register` blocks from a flat argv list."""
    if connection_class is None and store is None:
        msg = "register_ephemeral_connections requires either store= or connection_class"
        raise TypeError(msg)
    if connection_class is not None and store is None:
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
    """Return a read-only filtered view of `store`."""
    if scope is None:
        return store
    return _FilteredStore(store, scope)


# --------------------------------------------------------------------------- #
# Router (v0.3.1 — was Feature) — Pydantic-modeled router with auto-tagging.
# --------------------------------------------------------------------------- #


class Router(BaseModel, Generic[ConnT]):
    """Pydantic-modeled router: enricher + snapshot_dir + cassette_dir + register hooks.

    Subclass and instantiate, e.g. `IssuesRouter(name='issues', enricher=...)`.
    `register_read` / `register_write` are methods you override to register tools.

    `name` becomes a capability atom (auto-tagged onto every tool registered
    via this router, unless `auto_tag=False`).
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=False, extra="forbid")

    name: str = Field(pattern=r"^[a-z][a-z0-9_-]*$", description="Router slug.")
    capabilities: set[Capability] = Field(default_factory=set, description="Extra caps applied to all tools.")
    enricher: Any = None
    snapshot_dir: Path | None = None
    cassette_dir: Path | None = None
    default: bool = True
    auto_tag: bool = True

    def register_read(self, server: Any, store: Any) -> None:
        """Register read-only tools. Override in subclasses."""

    def register_write(self, server: Any, store: Any) -> None:
        """Register write-marked tools. Override in subclasses."""


class RouterRegistry:
    """Registry of routers — supports v0.3.1 Router instances + v0.3 decorator.

    `apply()` sets the active router context (read by the fat decorator's
    auto-tag seam) before invoking each `register_read` / `register_write`.
    """

    def __init__(self) -> None:
        self._routers: list[tuple[str, bool, Any]] = []

    def add(self, router: Router) -> Router:
        """Register a `Router` instance. Returns the instance for chaining."""
        # Pydantic enforces `name` is non-empty (`pattern=...`); no extra check needed.
        self._routers.append((router.name, router.default, router))
        return router

    def router(self, name: str, *, default: bool = True) -> Any:
        """Register a router class via decorator. v0.3.1 form."""

        def decorator(cls: Any) -> Any:
            self._routers.append((name, default, cls))
            return cls

        return decorator

    def feature(self, name: str, *, default: bool = False) -> Any:
        """Deprecated: use `.router()`."""
        warnings.warn(
            "FeatureRegistry.feature() / RouterRegistry.feature() is deprecated; use .router() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.router(name, default=default)

    def names(self) -> list[str]:
        """Return ordered router names."""
        return [name for name, _default, _r in self._routers]

    def feature_names(self) -> list[str]:
        """Deprecated alias for `.names()`."""
        return self.names()

    def defaults(self) -> set[str]:
        """Return the set of names enabled-by-default."""
        return {name for name, default, _r in self._routers if default}

    def apply(
        self,
        server: Any,
        store: Any,
        *,
        enabled: Iterable[str] | None = None,
        include_writes: bool = False,
    ) -> list[str]:
        """Register read tools (always) and write tools (if `include_writes`).

        Sets the active-router thread-local before calling each register hook
        so the fat decorator can auto-tag.
        """
        wanted = set(enabled) if enabled is not None else self.defaults()
        unknown = wanted - {name for name, _d, _r in self._routers}
        if unknown:
            msg = f"Unknown router(s): {sorted(unknown)}; available: {self.names()}"
            raise ValueError(msg)
        applied: list[str] = []
        for name, _default, item in self._routers:
            if name not in wanted:
                continue
            router_obj = item if isinstance(item, Router) else None
            try:
                if router_obj is not None:
                    _set_active(router_obj, "read")
                if hasattr(item, "register_read"):
                    item.register_read(server, store)
                if include_writes and hasattr(item, "register_write"):
                    if router_obj is not None:
                        _set_active(router_obj, "write")
                    item.register_write(server, store)
            finally:
                _set_active(None, None)
            applied.append(name)
        return applied


# Deprecation aliases: Feature / FeatureRegistry remain available one cycle.


class Feature(Router):
    """Deprecated: renamed to `Router`. Retained for one cycle.

    Supports v0.3 class-attribute style (`class IssuesFeature(Feature): name = "issues"`)
    by reading attributes off the subclass and feeding them to the BaseModel init.
    """

    name: str = "_feature_placeholder"  # type: ignore[assignment]
    default: bool = False  # type: ignore[assignment]

    def __init_subclass__(cls, **kw: Any) -> None:
        super().__init_subclass__(**kw)
        warnings.warn(
            f"`Feature` is deprecated; subclass `Router` instead (used by {cls.__name__}).",
            DeprecationWarning,
            stacklevel=2,
        )

    def __init__(self, **kw: Any) -> None:
        # Pull v0.3 class-level attributes if instance kwargs don't override.
        for attr in ("name", "default", "enricher", "snapshot_dir", "cassette_dir"):
            if attr not in kw:
                cls_val = type(self).__dict__.get(attr)
                if cls_val is not None:
                    kw[attr] = cls_val
        # Bare Feature() instantiation (base class) is allowed for legacy tests
        # that exercise the no-op register methods. Subclasses must set name.
        if type(self) is not Feature and (not kw.get("name") or kw.get("name") == "_feature_placeholder"):
            msg = f"{type(self).__name__}.name must be a non-empty string"
            raise ValueError(msg)
        kw.setdefault("name", "_feature_base")
        super().__init__(**kw)


class FeatureRegistry(RouterRegistry):
    """Deprecated: renamed to `RouterRegistry`. Retained for one cycle."""


# --------------------------------------------------------------------------- #
# MCPRunner — flag parsing + transport selection.
# --------------------------------------------------------------------------- #


class MCPRunner:
    """Wraps `server.run()` to handle `--register`, `--scope`, `--select`, `--http`.

    v0.3.1: replaces `--enable` / `--no-enable` / `--writes` with a single
    `--select` boolean expression. The deprecated flags are still parsed and
    translated to a `--select` expression with a `DeprecationWarning`.
    """

    def __init__(
        self,
        server: Any,
        *,
        store: Any | None = None,
        feature_registry: RouterRegistry | None = None,
        router_registry: RouterRegistry | None = None,
        connection_class: type[ConnectionInfo] | None = None,
        name: str = "a2kit",
        default_select: SelectExpr | str | None = None,
    ) -> None:
        if connection_class is not None:
            warnings.warn(
                "MCPRunner(connection_class=...) is deprecated; pass `store=` instead. The store knows its model.",
                DeprecationWarning,
                stacklevel=2,
            )
        if feature_registry is not None and router_registry is None:
            # `feature_registry` retained without warning — it's a kwarg name only;
            # the underlying class is now `RouterRegistry`. Migrate at leisure.
            router_registry = feature_registry
        self.server = server
        self.store = store
        self.router_registry = router_registry
        self.feature_registry = router_registry  # backcompat alias
        if connection_class is None and store is not None:
            connection_class = store.connection_class
        self.connection_class = connection_class
        self.name = name
        if isinstance(default_select, str):
            default_select = parse_select(default_select)
        self.default_select: SelectExpr = default_select or default_select_expr()

    def _parse(self, argv: list[str]) -> dict[str, Any]:  # noqa: C901
        i = 0
        result: dict[str, Any] = {
            "scope": None,
            "select": None,
            "http": None,
            "register_args": [],
            # deprecated v0.3 flags:
            "enable": None,
            "no_enable": set(),
            "writes": False,
        }
        while i < len(argv):
            a = argv[i]
            if a == "--scope" and i + 1 < len(argv):
                result["scope"] = argv[i + 1]
                i += 2
            elif a == "--select" and i + 1 < len(argv):
                result["select"] = argv[i + 1]
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
                if i + 1 < len(argv) and not argv[i + 1].startswith("--"):
                    result["http"] = argv[i + 1]
                    i += 2
                else:
                    result["http"] = ""
                    i += 1
            elif a == "--register":
                result["register_args"].append(a)
                i += 1
                while i < len(argv) and not argv[i].startswith("--"):
                    result["register_args"].append(argv[i])
                    i += 1
            else:
                i += 1
        return result

    def _legacy_to_select(self, parsed: dict[str, Any]) -> SelectExpr | None:
        """Translate deprecated v0.3 --enable/--no-enable/--writes into a SelectExpr."""
        if parsed["enable"] is None and not parsed["no_enable"] and not parsed["writes"]:
            return None
        warnings.warn(
            '--enable/--no-enable/--writes are deprecated; use --select "<expr>" instead.',
            DeprecationWarning,
            stacklevel=2,
        )
        parts: list[str] = []
        if parsed["enable"] is None:
            parts.append("default")
        else:
            chosen = " or ".join(f"router:{n}" for n in parsed["enable"])
            parts.append(f"({chosen})")
        parts.extend(f"not router:{excluded}" for excluded in parsed["no_enable"])
        # Mention `write` either way so `_expr_mentions(expr, 'write')` triggers
        # include_writes when --writes is on (and stays excluded when off).
        if parsed["writes"]:
            parts.append("(read or write)")
        else:
            parts.append("not write")
        return parse_select(" and ".join(parts))

    def _select_expr(self, parsed: dict[str, Any]) -> SelectExpr:
        """Resolve effective SelectExpr from CLI."""
        if parsed["select"] is not None:
            return parse_select(parsed["select"])
        legacy = self._legacy_to_select(parsed)
        return legacy if legacy is not None else self.default_select

    def _apply_routers(self, parsed: dict[str, Any]) -> SelectExpr:
        """Apply routers honouring the resolved --select expression. Returns the expr."""
        expr = self._select_expr(parsed)
        if self.router_registry is None:
            return expr
        # Routers needed: any whose name appears in the expression OR the defaults.
        wanted = self._wanted_routers(expr)
        # Validate atoms post-hoc against the union of registered routers (best-effort).
        # The lint rule (A2K010, future) covers source-time validation; runtime stays lax.
        import contextlib  # noqa: PLC0415

        with contextlib.suppress(Exception):
            validate_atoms(expr, known_routers=set(self.router_registry.names()), known_tools=set())
        # Determine include_writes: any branch references write.
        include_writes = _expr_mentions(expr, "write") or _expr_mentions(expr, "destructive")
        self.router_registry.apply(self.server, self.store, enabled=wanted, include_writes=include_writes)
        return expr

    def _wanted_routers(self, expr: SelectExpr) -> set[str]:
        """Best-effort: which routers should `apply()` register?

        Heuristic: if `default` is mentioned (positive) → start from defaults;
        otherwise start from explicitly-named routers. Negated atoms are removed.
        """
        assert self.router_registry is not None  # noqa: S101
        all_names = set(self.router_registry.names())
        mentions = _atom_polarity(expr)
        positive = {n for (n, ns), pol in mentions.items() if pol == "pos" and ns in (None, "router")}
        negative = {n for (n, ns), pol in mentions.items() if pol == "neg" and ns in (None, "router")}
        wanted: set[str]
        if "default" in positive:
            wanted = self.router_registry.defaults() | (positive & all_names)
        else:
            wanted = positive & all_names
            if not wanted:
                wanted = self.router_registry.defaults()
        wanted -= negative & all_names
        return wanted

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
        """Parse argv, register routers, set transport seam, run the server."""
        from a2kit.tools import _set_current_transport  # noqa: PLC0415

        argv = list(sys.argv[1:]) if argv is None else list(argv)
        parsed = self._parse(argv)
        ephemeral = self._ephemeral(parsed)
        parsed["ephemeral"] = ephemeral
        parsed["effective_select"] = self._apply_routers(parsed)

        chosen = transport
        if chosen is None:
            chosen = "http" if parsed["http"] is not None else "stdio"

        _set_current_transport(chosen)
        try:
            if chosen == "http":
                host, port = self._http_settings(parsed["http"] or "")
                self.server.settings.host = host
                self.server.settings.port = port
                self.server.run(transport="streamable-http")
            else:
                self.server.run(transport="stdio")
        finally:
            _set_current_transport(None)
        return parsed


def _expr_mentions(expr: SelectExpr, name: str) -> bool:
    """True if `name` appears as an atom anywhere in `expr` (any namespace or none)."""
    if expr.op == "atom":
        assert expr.atom is not None  # noqa: S101
        return expr.atom.name == name
    return any(_expr_mentions(c, name) for c in expr.children)


def _atom_polarity(expr: SelectExpr, _negated: bool = False) -> dict[tuple[str, str | None], str]:
    """Walk `expr`, return {(name, namespace): 'pos'|'neg'}.

    Best-effort: tracks whether each atom is under an even/odd number of `not`s.
    Mixed-polarity atoms collapse to whichever first appeared.
    """
    out: dict[tuple[str, str | None], str] = {}
    if expr.op == "atom":
        assert expr.atom is not None  # noqa: S101
        out[(expr.atom.name, expr.atom.namespace)] = "neg" if _negated else "pos"
        return out
    next_neg = not _negated if expr.op == "not" else _negated
    for c in expr.children:
        for k, v in _atom_polarity(c, next_neg).items():
            out.setdefault(k, v)
    return out


__all__ = [
    "Feature",
    "FeatureRegistry",
    "MCPRunner",
    "Router",
    "RouterRegistry",
    "build_cli",
    "register_ephemeral_connections",
    "scope_filter",
]
