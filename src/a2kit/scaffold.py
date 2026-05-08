"""CLI/MCP entrypoint scaffolding helpers.

Provides building blocks — NOT a `main()`. The MCP author owns the FastMCP server
instance and the program entry; a2kit only ships the recurring chunks.

v0.4: Removed all v0.3 deprecation aliases (clean cut, no external consumers).
The `Feature`/`FeatureRegistry` classes, the `--enable`/`--no-enable`/`--writes`
flags, and the `connection_class=` kwargs are gone. Migration recipes:

- `Feature` / `FeatureRegistry` → `Router` / `RouterRegistry` (kwarg init).
- `RouterRegistry.feature(name, ...)` → `RouterRegistry.router(name, ...)`.
- `--enable issues,sprints` → `--select "router:issues or router:sprints"`.
- `--no-enable sprints` → `--select "default and not router:sprints"`.
- `--writes` → include `(read or write)` in your `--select`.
- `build_cli(store, connection_class=...)` → `build_cli(store, ...)`.
- `MCPRunner(server, connection_class=...)` → `MCPRunner(server, store=store)`.
- `register_ephemeral_connections(args, connection_class)` → use `store=`.

v0.4 also auto-loads `[tool.a2kit.runner] default_select` and
`[tool.a2kit.capabilities]` from `pyproject.toml` (walks up from CWD).
"""

from __future__ import annotations

import re
import sys
import tomllib
import warnings
from collections.abc import Awaitable, Callable, Mapping  # noqa: F401  # `Awaitable`/`Callable` used by `EnricherFn` resolution
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Generic, NamedTuple, Protocol, TypeVar, Unpack, runtime_checkable

import click
from pydantic import BaseModel, ConfigDict, model_validator

from a2kit._capabilities import Cap, Capability, UnknownCapability, capabilities
from a2kit._context import _RouterContext
from a2kit._router_decorators import _make_decorator, _ToolBinding
from a2kit._router_state import _set_active
from a2kit._select import (
    SelectExpr,
    default_select_expr,
    parse_select,
    validate_atoms,
)
from a2kit.connections import ConnectionInfo, ConnectionStore, ConnectionStoreLike
from a2kit.enrichers import EnricherFn
from a2kit.exceptions import ConnectionNotFound
from a2kit.tokens import ResolverRegistry

if TYPE_CHECKING:
    from collections.abc import Iterable

    from a2kit._tool_kwargs import ToolKwargs

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


class _EphemeralAwareStore:
    """Private store-proxy: short-circuits `.load()` to an ephemeral dict before
    delegating to the base store. Used by `Router._apply_bindings` to lift
    ephemeral handling out of the tool decorator (v0.8).

    v0.10: `list_connections()` proxied so the auto-wired
    `connection_enricher` and connection-key schema enrichment can list
    base-store keys + ephemeral keys uniformly.
    """

    def __init__(
        self,
        base: Any,
        ephemeral: Mapping[tuple[str, ...], Any] | None,
    ) -> None:
        self._base = base
        self._ephemeral = dict(ephemeral) if ephemeral else {}

    async def load(self, key: tuple[str, ...]) -> Any:
        if key in self._ephemeral:
            return self._ephemeral[key]
        if self._base is None:
            raise ConnectionNotFound(key)
        return await self._base.load(key)

    async def list_connections(self) -> list[Any]:
        if self._base is not None and hasattr(self._base, "list_connections"):
            base_list = await self._base.list_connections()
        else:
            base_list = []
        existing_keys = {tuple(getattr(info, "key", ())) for info in base_list}
        merged = list(base_list)
        for key, info in self._ephemeral.items():
            if key not in existing_keys:
                merged.append(info)
        return merged


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

    connection_class = store.connection_class

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
        path = anyio.run(store.save, info)
        click.echo(f"Saved: {path}")

    @cli.command("logout")
    @click.argument("key")
    def logout(key: str) -> None:
        """Remove a saved connection."""
        try:
            anyio.run(store.delete, _parse_key_arg(key))
        except ConnectionNotFound as exc:
            raise click.ClickException(str(exc)) from exc
        click.echo(f"Removed: {key}")

    @cli.group("connections")
    def connections() -> None:
        """Manage saved connections."""

    @connections.command("list")
    def connections_list() -> None:
        """List all saved connections."""
        results = anyio.run(store.list_connections)
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
            info = anyio.run(store.load, _parse_key_arg(key))
        except ConnectionNotFound as exc:
            raise click.ClickException(str(exc)) from exc
        click.echo(info.model_dump_json(indent=2))

    @connections.command("delete")
    @click.argument("key")
    def connections_delete(key: str) -> None:
        """Delete a saved connection."""
        try:
            anyio.run(store.delete, _parse_key_arg(key))
        except ConnectionNotFound as exc:
            raise click.ClickException(str(exc)) from exc
        click.echo(f"Removed: {key}")

    return cli


def register_ephemeral_connections(
    args: list[str],
    *,
    store: ConnectionStore[C],
) -> dict[tuple[str, ...], C]:
    """Parse `--register` blocks from a flat argv list.

    v0.4: `store=` is required (the v0.3 positional-class shape is gone).
    """
    connection_class = store.connection_class
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


def _parse_multistore_register(
    args: list[str],
    stores_by_router: dict[str, Any],
) -> dict[tuple[str, ...], Any]:
    """Parse `--register router:key=...` for multi-store MCPs.

    Bare `--register key=...` (no `router:` prefix) raises a clear error
    listing the available router prefixes.
    """
    out: dict[tuple[str, ...], Any] = {}
    i = 0
    while i < len(args):
        if args[i] != "--register":
            i += 1
            continue
        if i + 1 >= len(args):
            msg = "--register requires a key argument"
            raise ValueError(msg)
        raw_key = args[i + 1]
        if ":" not in raw_key:
            msg = (
                f"--register {raw_key!r}: ambiguous in a multi-store MCP. "
                f"Use `router:key` form. Available routers: {sorted(stores_by_router)}."
            )
            raise ValueError(msg)
        router_name, key_part = raw_key.split(":", 1)
        if router_name not in stores_by_router:
            msg = f"--register {raw_key!r}: unknown router prefix {router_name!r}. Available: {sorted(stores_by_router)}."
            raise ValueError(msg)
        store = stores_by_router[router_name]
        connection_class = store.connection_class
        key_tuple = _parse_key_arg(key_part)
        kwargs: dict[str, Any] = {}
        j = i + 2
        while j < len(args) and args[j] != "--register":
            if "=" in args[j]:
                k, v = _parse_kv_pair(args[j])
                kwargs[k] = v
                j += 1
            else:
                break  # pragma: no cover — defensive against malformed input
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

    async def load(self, key: tuple[str, ...]) -> C:
        if not self._matches(key):
            raise ConnectionNotFound(key)
        return await self._store.load(key)

    async def list_connections(self) -> list[C]:
        return [info for info in await self._store.list_connections() if self._matches(info.key)]

    @property
    def config_dir(self) -> Any:
        return self._store.config_dir


def scope_filter(store: ConnectionStore[C], scope: str | None) -> Any:
    """Return a read-only filtered view of `store`."""
    if scope is None:
        return store
    return _FilteredStore(store, scope)


# --------------------------------------------------------------------------- #
# Router — Pydantic-modeled router with auto-tagging.
# --------------------------------------------------------------------------- #


_SLUG_RE = re.compile(r"^[a-z][a-z0-9_-]*$")
_CAMEL_BOUNDARY = re.compile(r"(?<!^)(?=[A-Z])")


def _slugify(class_name: str) -> str:
    """Convert a CamelCase class name (minus `Router` suffix) into a slug.

    `JiraConfluenceRouter` → `jira-confluence`
    `WidgetsRouter`        → `widgets`
    `Router`               → `""` (caller must validate / supply explicit name).
    """
    base = class_name.removesuffix("Router")
    if not base:
        return ""
    parts = _CAMEL_BOUNDARY.split(base)
    return "-".join(p.lower() for p in parts if p)


class Router(BaseModel, Generic[ConnT]):
    """Pydantic-modeled router with v0.6 ergonomics.

    Subclass it; the slug `name` is auto-derived from the class name (strip
    `Router` suffix, hyphenate CamelCase, lowercase). Override with explicit
    `name="..."` if needed.

    Use `@MyRouter.read/.write/.tool` classmethod decorators to bind tools.
    `register_read` / `register_write` walk `cls._tools` by default; override
    them for imperative dynamic-tool registration (escape hatch).

    Per-Router DI lifts to the class — `store`, `enricher`, `resolver_registry`,
    `ephemeral`. Per-tool overrides remain available on the decorator kwargs
    (except `ephemeral` — v0.8: ephemeral is a Router-level concern only and is
    merged into the effective store via `_EphemeralAwareStore`).

    `name` is auto-tagged onto every registered tool (unless `auto_tag=False`).
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=False, extra="forbid")

    # Identity:
    name: str = ""

    # Caps configuration — class-level (a router's caps describe its TYPE):
    capabilities: ClassVar[set[Capability]] = set()
    read_capabilities: ClassVar[set[Capability]] = {Cap.READ}
    write_capabilities: ClassVar[set[Capability]] = {Cap.WRITE}

    # DI (router-level — inherited by every tool the router registers):
    # v0.11: typed via Protocols / type aliases (was `Any`). Pydantic still
    # accepts these because `arbitrary_types_allowed=True`; ty / IDEs now see
    # the real shape on every consumer.
    store: ConnectionStoreLike | None = None
    enricher: EnricherFn | None = None
    resolver_registry: ResolverRegistry | None = None
    # `Mapping` is covariant in the value type → callers can pass
    # `dict[tuple[str, ...], MyConn]` for any `MyConn <: ConnectionInfo`.
    ephemeral: Mapping[tuple[str, ...], ConnectionInfo] | None = None

    # Existing fields:
    snapshot_dir: Path | None = None
    cassette_dir: Path | None = None
    default: bool = True
    auto_tag: bool = True

    # v0.10: when True (default) AND `store` is set AND no explicit `enricher`
    # is provided, the kit wires `connection_enricher(store)` so a typo in the
    # `connection` arg returns "Did you mean…?" instead of a raw KeyError.
    auto_connection_enricher: bool = True

    # Per-subclass tool registry — populated by `@cls.read/.write/.tool` decorators.
    # Each subclass gets a fresh empty list via `__init_subclass__`.
    _tools: ClassVar[list[_ToolBinding]] = []

    # Per-subclass typed ContextVar accessor — `cls.context.info()` returns ConnT.
    context: ClassVar[Any] = None  # set by __init_subclass__

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # Fresh per-subclass tool registry (avoid mutable-default-shared-with-parent).
        cls._tools = []
        # Build the per-subclass typed ContextVar accessor. Slug derived from name
        # at instantiation; we use the class name here to keep the ContextVar
        # name stable & unique even if instances customise `name=`.
        # FQN-based naming (v0.7) — collision-free across modules.
        fqn = f"{cls.__module__}.{cls.__qualname__}"
        cls.context = _RouterContext(router_name=cls.__name__, fqn=fqn)

    @model_validator(mode="before")
    @classmethod
    def _default_name(cls, values: Any) -> Any:
        """Auto-derive `name` from the class name when not explicitly provided."""
        if isinstance(values, dict) and not values.get("name"):
            slug = _slugify(cls.__name__)
            if slug and _SLUG_RE.match(slug):
                values["name"] = slug
        return values

    @model_validator(mode="after")
    def _validate_slug(self) -> Router[ConnT]:
        if not _SLUG_RE.match(self.name):
            msg = f"Router.name {self.name!r} must match pattern {_SLUG_RE.pattern}"
            raise ValueError(msg)
        return self

    # --- Decorator factories — record bindings at class-body-eval time. -----

    @classmethod
    def tool(cls, **kwargs: Unpack[ToolKwargs]) -> Any:
        """Underlying primitive — register a tool on this router with explicit caps."""
        return _make_decorator(cls, mode="tool", decorator_kwargs=dict(**kwargs))

    @classmethod
    def read(cls, **kwargs: Unpack[ToolKwargs]) -> Any:
        """Register a read-mode tool. Effective caps include `cls.read_capabilities`."""
        return _make_decorator(cls, mode="read", decorator_kwargs=dict(**kwargs))

    @classmethod
    def write(cls, **kwargs: Unpack[ToolKwargs]) -> Any:
        """Register a write-mode tool. Effective caps include `cls.write_capabilities`."""
        return _make_decorator(cls, mode="write", decorator_kwargs=dict(**kwargs))

    # --- Default register_* impls — walk _tools, build effective tool kwargs. -

    def register_read(self, server: Any, store: Any) -> None:
        """Walk `cls._tools` (mode in {'read','tool'}) and register on `server`.

        Override for imperative / dynamic registration.
        """
        self._apply_bindings(server, store, mode_filter={"read", "tool"})

    def register_write(self, server: Any, store: Any) -> None:
        """Walk `cls._tools` (mode='write') and register on `server`."""
        self._apply_bindings(server, store, mode_filter={"write"})

    def _apply_bindings(self, server: Any, store: Any, *, mode_filter: set[str]) -> None:
        """Iterate `cls._tools`, call `@a2kit.tool(...)` with merged kwargs."""
        from a2kit.enrichers import connection_enricher as _connection_enricher  # noqa: PLC0415
        from a2kit.tools import tool as _tool_decorator  # noqa: PLC0415

        base_store = self.store if self.store is not None else store
        # Lift ephemeral connections to the store layer — the tool decorator
        # itself never sees them (v0.8: no `ephemeral=` kwarg on @a2kit.tool).
        effective_store = _EphemeralAwareStore(base_store, self.ephemeral) if self.ephemeral else base_store
        # v0.10: auto-wire connection_enricher when the router has a store and
        # no explicit enricher is configured. Author can disable by setting
        # `auto_connection_enricher=False` on the Router subclass.
        default_enricher: Any = self.enricher
        if default_enricher is None and effective_store is not None and self.auto_connection_enricher:
            default_enricher = _connection_enricher(effective_store)
        for binding in self._tools:
            if binding.mode not in mode_filter:
                continue
            merged: dict[str, Any] = {
                "server": server,
                "store": effective_store,
                "enricher": default_enricher,
                "resolver_registry": self.resolver_registry,
                "router_context": self.__class__.context,
            }
            # `@Router.tool()` is the no-connection escape hatch — opt out of
            # connection auto-inject. `.read()`/`.write()` keep the default.
            if binding.mode == "tool":
                merged["connection"] = False
            # Per-tool decorator kwargs win over router DI.
            merged.update(binding.decorator_kwargs)
            # Compute write/capabilities sugar.
            extra_caps: set[Capability] = set(binding.capabilities)
            if binding.mode == "read":
                extra_caps |= self.__class__.read_capabilities
            elif binding.mode == "write":
                extra_caps |= self.__class__.write_capabilities
                merged.setdefault("write", True)
            existing_caps = set(merged.get("capabilities", set()) or set())
            merged["capabilities"] = existing_caps | extra_caps
            _tool_decorator(**merged)(binding.fn)


@runtime_checkable
class _RegisterableRouter(Protocol):
    """Internal Protocol — what `RouterRegistry.apply` actually needs from each entry.

    Both `Router` instances and decorator-registered classes satisfy this
    structurally. Defined here (not exported) to make the duck-typing in
    `apply()` legible to ty / IDEs and to remove the `hasattr(...)` branches.
    """

    def register_read(self, server: Any, store: Any) -> None: ...

    def register_write(self, server: Any, store: Any) -> None: ...


class _RouterEntry(NamedTuple):
    """One row in `RouterRegistry._routers`. Replaces the v0.10 raw 3-tuple."""

    name: str
    default: bool
    item: Any  # `Router` instance or decorator-registered class — duck-typed


class RouterRegistry:
    """Registry of routers — supports `Router` instances and class-decorator form."""

    def __init__(self) -> None:
        self._routers: list[_RouterEntry] = []

    def add(self, router: Router) -> Router:
        """Register a `Router` instance. Returns the instance for chaining."""
        self._routers.append(_RouterEntry(router.name, router.default, router))
        return router

    def router(self, name: str, *, default: bool = True) -> Any:
        """Register a router class via decorator."""

        def decorator(cls: Any) -> Any:
            self._routers.append(_RouterEntry(name, default, cls))
            return cls

        return decorator

    def names(self) -> list[str]:
        """Return ordered router names."""
        return [entry.name for entry in self._routers]

    def routers_with_stores(self, fallback_store: Any = None) -> list[tuple[str, Any]]:
        """Return [(router_name, store)] for routers that have a store (own or inherited).

        v0.6: each `Router` instance may have its own `store=`. If not, the
        runner-level `fallback_store` is used.
        """
        out: list[tuple[str, Any]] = []
        for entry in self._routers:
            router_store = getattr(entry.item, "store", None)
            chosen = router_store if router_store is not None else fallback_store
            if chosen is not None:
                out.append((entry.name, chosen))
        return out

    def defaults(self) -> set[str]:
        """Return the set of names enabled-by-default."""
        return {entry.name for entry in self._routers if entry.default}

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
        unknown = wanted - {entry.name for entry in self._routers}
        if unknown:
            msg = f"Unknown router(s): {sorted(unknown)}; available: {self.names()}"
            raise ValueError(msg)
        applied: list[str] = []
        for entry in self._routers:
            if entry.name not in wanted:
                continue
            item = entry.item
            router_obj = item if isinstance(item, Router) else None
            # v0.6: per-router store wins over the runner-level fallback.
            effective_store = getattr(item, "store", None) or store
            try:
                if router_obj is not None:
                    _set_active(router_obj, "read")
                if hasattr(item, "register_read"):
                    item.register_read(server, effective_store)
                if include_writes and hasattr(item, "register_write"):
                    if router_obj is not None:
                        _set_active(router_obj, "write")
                    item.register_write(server, effective_store)
            finally:
                _set_active(None, None)
            applied.append(entry.name)
        return applied


# --------------------------------------------------------------------------- #
# pyproject.toml loader — walks up from CWD.
# --------------------------------------------------------------------------- #


def _find_pyproject(start: Path | None = None) -> Path | None:
    """Walk up from `start` (default CWD) to find a pyproject.toml."""
    cur = (start or Path.cwd()).resolve()
    for parent in [cur, *cur.parents]:
        candidate = parent / "pyproject.toml"
        if candidate.is_file():
            return candidate
    return None


def _load_pyproject_a2kit() -> dict[str, Any]:
    """Read `[tool.a2kit]` from the nearest pyproject.toml; empty dict if none."""
    path = _find_pyproject()
    if path is None:
        return {}
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    tool = data.get("tool", {})
    if not isinstance(tool, dict):  # pragma: no cover — TOML-impossible
        return {}
    a2k = tool.get("a2kit", {})
    return a2k if isinstance(a2k, dict) else {}


def _register_pyproject_capabilities(a2kit_table: dict[str, Any]) -> None:
    """Register entries under `[tool.a2kit.capabilities]` into the global registry.

    Each entry: `"name" = { description = "...", aliases = [...] }`. Bad entries
    raise `ValueError` so misconfiguration surfaces at startup.
    """
    caps_table = a2kit_table.get("capabilities", {})
    if not caps_table:
        return
    if not isinstance(caps_table, dict):
        msg = "[tool.a2kit.capabilities] must be a table of name -> {description, aliases}"
        raise ValueError(msg)
    for name, body in caps_table.items():
        # TOML key-uniqueness is enforced at parse time; no need to dedupe here.
        if not isinstance(body, dict):
            msg = f"Capability {name!r} body must be a table; got {type(body).__name__}"
            raise ValueError(msg)
        capabilities.register(
            name,
            description=body.get("description", ""),
            aliases=list(body.get("aliases", []) or []),
        )


@runtime_checkable
class FastMCPLike(Protocol):
    """Minimum FastMCP server surface a2kit drives.

    Any object passed to `MCPRunner(server, ...)` must satisfy this. The Protocol
    is intentionally loose: nested `settings` is `Any` because we only assign
    `settings.host` / `settings.port` at HTTP startup, and pinning the inner
    shape would reject test fakes for no real safety win. Private surfaces
    (`_tool_manager`) are accessed with `getattr` and not encoded here.
    """

    settings: Any

    def tool(self, *args: Any, **kwargs: Any) -> Any: ...
    def run(self, *args: Any, **kwargs: Any) -> Any: ...


# --------------------------------------------------------------------------- #
# MCPRunner — flag parsing + transport selection.
# --------------------------------------------------------------------------- #


class MCPRunner:
    """Wraps `server.run()` to handle `--register`, `--scope`, `--select`, `--http`.

    v0.4: `--enable` / `--no-enable` / `--writes` are gone. Only `--select`
    remains. `default_select` resolves in order: explicit kwarg →
    `[tool.a2kit.runner] default_select` in pyproject.toml → hard default
    `"default and not write and not destructive"`.

    pyproject.toml is walked up from CWD on init; `[tool.a2kit.capabilities]`
    entries are auto-registered.
    """

    def __init__(
        self,
        server: FastMCPLike,
        *,
        store: ConnectionStore[Any] | None = None,
        router_registry: RouterRegistry | None = None,
        name: str = "a2kit",
        default_select: SelectExpr | str | None = None,
    ) -> None:
        self.server: FastMCPLike = server
        self.store: ConnectionStore[Any] | None = store
        self.router_registry = router_registry
        self.connection_class = store.connection_class if store is not None else None
        self.name = name

        a2kit_table = _load_pyproject_a2kit()
        # Register pyproject-declared capabilities first so `default_select`
        # validation can resolve their atoms.
        _register_pyproject_capabilities(a2kit_table)

        self.default_select: SelectExpr = self._resolve_default_select(default_select, a2kit_table)

    @staticmethod
    def _resolve_default_select(
        explicit: SelectExpr | str | None,
        a2kit_table: dict[str, Any],
    ) -> SelectExpr:
        """Resolution order: explicit kwarg → pyproject value → hard default."""
        if isinstance(explicit, SelectExpr):
            return explicit
        if isinstance(explicit, str):
            return parse_select(explicit)
        runner_table = a2kit_table.get("runner", {})
        pyp_value = runner_table.get("default_select") if isinstance(runner_table, dict) else None
        if isinstance(pyp_value, str):
            try:
                return parse_select(pyp_value)
            except (ValueError, UnknownCapability) as exc:
                warnings.warn(
                    f"[tool.a2kit.runner] default_select={pyp_value!r} failed to parse: {exc}; falling back to the hard-coded default.",
                    UserWarning,
                    stacklevel=3,
                )
        return default_select_expr()

    def _parse(self, argv: list[str]) -> dict[str, Any]:
        i = 0
        result: dict[str, Any] = {
            "scope": None,
            "select": None,
            "http": None,
            "register_args": [],
        }
        while i < len(argv):
            a = argv[i]
            if a == "--scope" and i + 1 < len(argv):
                result["scope"] = argv[i + 1]
                i += 2
            elif a == "--select" and i + 1 < len(argv):
                result["select"] = argv[i + 1]
                i += 2
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

    def _select_expr(self, parsed: dict[str, Any]) -> SelectExpr:
        """Resolve effective SelectExpr from CLI."""
        if parsed["select"] is not None:
            return parse_select(parsed["select"])
        return self.default_select

    def _apply_routers(self, parsed: dict[str, Any]) -> SelectExpr:
        """Apply routers honouring the resolved --select expression. Returns the expr."""
        expr = self._select_expr(parsed)
        if self.router_registry is None:
            return expr
        wanted = self._wanted_routers(expr)
        # Best-effort post-hoc validation; the lint rule (A2K010) covers source-time.
        import contextlib  # noqa: PLC0415

        with contextlib.suppress(Exception):
            validate_atoms(expr, known_routers=set(self.router_registry.names()), known_tools=set())
        include_writes = _expr_mentions(expr, "write") or _expr_mentions(expr, "destructive")
        self.router_registry.apply(self.server, self.store, enabled=wanted, include_writes=include_writes)
        return expr

    def _wanted_routers(self, expr: SelectExpr) -> set[str]:
        """Best-effort: which routers should `apply()` register?"""
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
        if not parsed["register_args"]:
            return {}
        # v0.6: when multiple routers carry their own stores, the bare
        # `--register key=...` form is ambiguous. Require `router:key` namespacing.
        if self.router_registry is not None:
            stores_by_router = dict(self.router_registry.routers_with_stores(fallback_store=self.store))
            distinct_stores = {id(s) for s in stores_by_router.values()}
            if len(distinct_stores) > 1:
                return _parse_multistore_register(parsed["register_args"], stores_by_router)
        if self.store is None:
            return {}
        return register_ephemeral_connections(parsed["register_args"], store=self.store)

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

    def _prepare(self, argv: list[str] | None, transport: str | None) -> tuple[dict[str, Any], str]:
        """Parse argv, register routers, decide transport. Pure-sync orchestration —
        shared by `run` (sync entry) and `run_async` (embedded entry)."""
        argv = list(sys.argv[1:]) if argv is None else list(argv)
        parsed = self._parse(argv)
        ephemeral = self._ephemeral(parsed)
        parsed["ephemeral"] = ephemeral
        parsed["effective_select"] = self._apply_routers(parsed)

        chosen = transport
        if chosen is None:
            chosen = "http" if parsed["http"] is not None else "stdio"

        if chosen == "http":
            host, port = self._http_settings(parsed["http"] or "")
            self.server.settings.host = host
            self.server.settings.port = port
        return parsed, chosen

    def run(self, argv: list[str] | None = None, *, transport: str | None = None) -> dict[str, Any]:
        """Parse argv, register routers, set transport seam, run the server."""
        from a2kit.tools import _set_current_transport  # noqa: PLC0415

        parsed, chosen = self._prepare(argv, transport)
        _set_current_transport(chosen)
        try:
            if chosen == "http":
                self.server.run(transport="streamable-http")
            else:
                self.server.run(transport="stdio")
        finally:
            _set_current_transport(None)
        return parsed

    async def run_async(self, argv: list[str] | None = None, *, transport: str | None = None) -> dict[str, Any]:
        """Async entry — for embedding a2kit inside a host that already runs an event loop.

        Awaits `server.run_async(...)` when the FastMCP server exposes it.
        Falls back to a clear error otherwise — running the blocking sync
        `server.run` from inside a host loop would deadlock or starve other
        tasks, so we don't try to paper over that.
        """
        from a2kit.tools import _set_current_transport  # noqa: PLC0415

        run_async = getattr(self.server, "run_async", None)
        if run_async is None:
            msg = (
                f"{type(self.server).__name__}.run_async is not defined. "
                "Use `runner.run(...)` from a sync entry point, or upgrade your "
                "FastMCP server to a version that exposes `run_async`."
            )
            raise RuntimeError(msg)

        parsed, chosen = self._prepare(argv, transport)
        _set_current_transport(chosen)
        try:
            if chosen == "http":
                await run_async(transport="streamable-http")
            else:
                await run_async(transport="stdio")
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
    """Walk `expr`, return {(name, namespace): 'pos'|'neg'}."""
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
    "FastMCPLike",
    "MCPRunner",
    "Router",
    "RouterRegistry",
    "build_cli",
    "register_ephemeral_connections",
    "scope_filter",
]
