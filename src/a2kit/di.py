"""Dependency-injection types for v0.12.

a2kit's DI is intentionally tiny — three Protocols and one convenience base.
The runner consumes these (see `MCPRunner(server, provides=[...], plugins=[...])`),
but this module defines no wiring. Pure types.

Mental model:
    A **Provider** produces values of one type. The runner builds a
    `dict[type, Provider]` at startup; tools declare typed kwonly params and
    the runner pre-binds each param to its provider.

    A **Plugin** bundles providers + Click commands + lifecycle hooks. It's
    how a feature (Connections, Cassettes, OTel meter, Secret resolvers)
    extends the runner without the runner needing to know what it is.

Concrete provider example (will live in a connections plugin in v0.13):

    class ConnectionStoreProvider:
        provides = JiraConn
        async def get(self, key: tuple[str, ...] = ("default",)) -> JiraConn:
            return await load_from_disk(key)
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    import click


@runtime_checkable
class Provider(Protocol):
    """Produces values of `provides` for injection into tool params.

    The kit dispatches by type: a tool param annotated `T` is bound to the
    provider whose `provides == T`. Subclass relationships do NOT auto-resolve
    in v0.12 — declare distinct types if you need parallel instances.

    `get` may take call-scoped kwargs (e.g. the connection key, request
    metadata). The runner passes whatever the binding-resolution layer
    extracts from the call site; provider implementations document what they
    accept.
    """

    provides: type
    """The exact type produced by this provider. Used as the dispatch key."""

    async def get(self, **ctx: Any) -> Any:
        """Produce one instance of `self.provides`. Async — providers
        commonly do I/O (load from disk, API call).
        """
        ...


@runtime_checkable
class Plugin(Protocol):
    """Runner extension. Bundles providers + Click commands + lifecycle hooks.

    All members except `name` are optional in practice — `PluginBase` supplies
    safe defaults so a 1-feature plugin only sets what it uses.
    """

    name: str
    """Plugin name. Used as the OTel span prefix (`a2kit.plugin.{name}`),
    in error messages, and as a discriminator for plugin-vs-plugin
    interactions. Should be a slug (`connections`, `cassettes`)."""

    providers: list[Provider]
    """Type-providers this plugin contributes to the runner's DI registry."""

    commands: list[click.Command]
    """Click commands this plugin contributes to the host CLI. The runner
    aggregates these into the parent `click.Group` at CLI build time."""

    async def on_startup(self, runner: Any) -> None:
        """Called once after the runner has finished compiling tool plans
        but before serving the first request. Plugins use this for lazy
        connection establishment, schema warm-ups, etc.
        """
        ...

    async def on_shutdown(self, runner: Any) -> None:
        """Called once during runner teardown. Plugins use this for
        flushing buffers, closing connections, etc. Called in reverse
        registration order.
        """
        ...


class PluginBase:
    """Convenience base — set `name`, override what you need.

    A 1-method plugin = subclass `PluginBase`, set `name`, add one of
    `providers` / `commands` / lifecycle hooks. Other slots stay empty.

    Future Plugin Protocol extensions (e.g. `middleware: list[Middleware]`)
    add a class attribute with `[]` default; runner reads via
    `getattr(plugin, "middleware", [])`. No Protocol churn.
    """

    name: str = ""
    providers: list[Provider] = []  # noqa: RUF012 — class-level default; subclasses override
    commands: list[click.Command] = []  # noqa: RUF012

    async def on_startup(self, runner: Any) -> None:
        """No-op by default."""

    async def on_shutdown(self, runner: Any) -> None:
        """No-op by default."""


@dataclass(frozen=True, slots=True)
class Binding:
    """One resolved param-to-provider binding for a tool plan."""

    param_name: str
    provider: Provider


@dataclass(frozen=True, slots=True)
class ToolPlan:
    """Pre-compiled wiring for one tool. Built at runner startup.

    `bindings` lists kit-injected DI params. `passthrough` lists params the
    MCP client provides (the agent-facing arguments). At call time:
    - resolve each binding's provider via `await provider.get(**ctx)`,
    - merge with passthrough kwargs from the client,
    - call the tool function.
    """

    fn: Any
    bindings: tuple[Binding, ...] = ()
    passthrough: tuple[str, ...] = ()


class ProviderCollisionError(Exception):
    """Two providers claim the same `provides` type. Raised at runner startup
    so misconfiguration surfaces before the first request.
    """

    def __init__(self, type_: type, first: type, second: type) -> None:
        self.type_ = type_
        self.first = first
        self.second = second
        super().__init__(
            f"Provider collision for {type_.__name__}: "
            f"{first.__name__} vs {second.__name__}. "
            "Each type must have exactly one provider in v0.12."
        )


class UnknownProviderTypeError(Exception):
    """A tool param is annotated with a type that has no registered provider.
    Raised at runner startup so missing wiring surfaces before the first
    request.
    """

    def __init__(self, tool_name: str, param_name: str, type_: type) -> None:
        self.tool_name = tool_name
        self.param_name = param_name
        self.type_ = type_
        super().__init__(
            f"Tool {tool_name!r} param {param_name!r} is annotated "
            f"as {type_.__name__} but no provider is registered for that "
            "type. Add a provider to `MCPRunner(..., provides=[...])` or via "
            "a plugin."
        )


class UnknownProviderDepError(Exception):
    """A provider's `get` declares a typed kwonly dep that no other provider
    produces. Raised at runner startup, so misconfiguration surfaces before
    the first request rather than mid-chain."""

    def __init__(self, owner_type: type, dep_name: str, dep_type: type) -> None:
        self.owner_type = owner_type
        self.dep_name = dep_name
        self.dep_type = dep_type
        super().__init__(
            f"Provider for {owner_type.__name__} declares kwonly dep "
            f"{dep_name!r}: {dep_type.__name__} but no provider is registered "
            f"for {dep_type.__name__}. Add one via "
            f"`MCPRunner(..., provides=[...])`."
        )


class ProviderCycleError(Exception):
    """Provider dep graph contains a cycle. Raised at runner startup."""

    def __init__(self, cycle: tuple[type, ...]) -> None:
        self.cycle = cycle
        names = " -> ".join(t.__name__ for t in cycle)
        super().__init__(f"Provider dependency cycle detected: {names}. Each chained provider's deps must form a DAG.")


def _provider_dep_types(provider: Provider) -> dict[str, type]:
    """Inspect `provider.get`; return `{param_name: type}` for typed kwonly
    deps. Skips `**ctx`, positional, and untyped params — only KEYWORD_ONLY
    params with a class annotation count as DI dependencies.

    Used by the runner's chained-resolution layer (Step 6, v0.12). Providers
    declare their deps simply by typing kwonly params on `get`:

        async def get(self, *, conn: TodoConn) -> TodoStore: ...

    The runner then resolves `TodoConn` first, passes it as `conn=`, and
    awaits `get(conn=...)`.
    """
    sig = inspect.signature(provider.get)
    try:
        hints = inspect.get_annotations(provider.get, eval_str=True)
    except (NameError, AttributeError, TypeError):
        # Fallback to raw annotations — non-class hints (strings, generics)
        # are filtered below.
        hints = getattr(provider.get, "__annotations__", {}) or {}
    out: dict[str, type] = {}
    for name, param in sig.parameters.items():
        if param.kind != inspect.Parameter.KEYWORD_ONLY:
            continue
        anno = hints.get(name)
        if isinstance(anno, type):
            out[name] = anno
    return out


def _check_deps_resolvable(index: dict[type, Provider], soft_known: frozenset[type]) -> None:
    """Ensure every provider's typed kwonly dep has a registered provider or
    is in `soft_known`. Raises `UnknownProviderDepError` on misconfiguration."""
    for owner_type, prov in index.items():
        for dep_name, dep_type in _provider_dep_types(prov).items():
            if dep_type in index or dep_type in soft_known:
                continue
            raise UnknownProviderDepError(owner_type, dep_name, dep_type)


def _check_no_cycles(index: dict[type, Provider]) -> None:
    """3-color DFS over the provider graph; raise `ProviderCycleError` on a back-edge."""
    WHITE, GRAY, BLACK = 0, 1, 2  # noqa: N806
    color: dict[type, int] = dict.fromkeys(index, WHITE)
    path: list[type] = []

    def dfs(t: type) -> None:
        color[t] = GRAY
        path.append(t)
        for dep_type in _provider_dep_types(index[t]).values():
            if dep_type not in color:
                # Soft-known dep (preloaded by the tool wrapper); graph leaf.
                continue
            if color[dep_type] == GRAY:
                start = path.index(dep_type)
                raise ProviderCycleError((*tuple(path[start:]), dep_type))
            if color[dep_type] == WHITE:
                dfs(dep_type)
        path.pop()
        color[t] = BLACK

    for t in list(index):
        if color[t] == WHITE:
            dfs(t)


def _validate_provider_graph(
    index: dict[type, Provider],
    *,
    soft_known: frozenset[type] = frozenset(),
) -> None:
    """Validate the type→provider graph: deps exist, no cycles. Raises
    `UnknownProviderDepError` or `ProviderCycleError` on misconfiguration.

    `soft_known` lists types the runner can satisfy via a non-provider path
    (e.g. `ConnectionInfo` subclasses preloaded by the connection store).
    These count as resolvable when a provider's `get` lists them as a kwonly
    dep, even though they don't appear in `index`.
    """
    _check_deps_resolvable(index, soft_known)
    _check_no_cycles(index)


async def resolve_chain(
    index: dict[type, Provider],
    type_: type,
    /,
    *,
    preloaded: dict[type, Any] | None = None,
    **call_ctx: Any,
) -> Any:
    """Async-resolve `type_` from `index`, chaining typed kwonly deps. Caches
    each resolved type within the call so a diamond doesn't re-instantiate.

    `preloaded` seeds the cache with already-resolved values — used by the
    tool wrapper to avoid double-loading the connection object when the tool
    has both `*, conn: TrackerConn` (already resolved by the prelude) and
    `*, store: TrackerStore` (resolves through `TrackerConn`).

    `call_ctx` is merged into each provider's `get(**)` for params not satisfied
    by chained deps (e.g. the connection key).
    """
    cache: dict[type, Any] = dict(preloaded) if preloaded else {}

    async def _r(t: type) -> Any:
        if t in cache:
            return cache[t]
        prov = index.get(t)
        if prov is None:
            raise UnknownProviderTypeError("(resolve)", "(root)", t)
        deps = _provider_dep_types(prov)
        kwargs: dict[str, Any] = {name: await _r(dep_type) for name, dep_type in deps.items()}
        for k, v in call_ctx.items():
            kwargs.setdefault(k, v)
        value = await prov.get(**kwargs)
        cache[t] = value
        return value

    return await _r(type_)


__all__ = [
    "Binding",
    "Plugin",
    "PluginBase",
    "Provider",
    "ProviderCollisionError",
    "ProviderCycleError",
    "ToolPlan",
    "UnknownProviderDepError",
    "UnknownProviderTypeError",
    "_provider_dep_types",
    "_validate_provider_graph",
    "resolve_chain",
]
