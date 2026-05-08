"""Verb decorators — thin wrappers around `@a2kit.tool` with shape defaults.

`@a2kit.list` — list-shaped tool. Many-out, no query in. Defaults filter /
fields / pagination to `Local`. Adds `Cap.READ`.

`@a2kit.read` — single complex query → result. Defaults list-view off (the
tool body owns its own filtering). Adds `Cap.READ`.

`@a2kit.write` — mutation. Defaults list-view off, `write=True`. Adds
`Cap.WRITE`.

All verbs accept the full `@a2kit.tool` kwarg surface — verb defaults are
the floor, not a ceiling. Author overrides win:

    @a2kit.list(filter=Passthrough)        # tool body owns filter; pagination/fields stay Local
    async def search_widgets(*, jira: JiraConn, filter: str) -> list[Widget]: ...

Usage matches `@a2kit.tool(...)` — always call with parens.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, Any, TypeVar

from a2kit._capabilities import Cap, Capability
from a2kit.formatter import ListViewMode, Local
from a2kit.tools._decorator import tool

if TYPE_CHECKING:
    from a2kit.connections import ConnectionStore
    from a2kit.enrichers import EnricherFn
    from a2kit.tokens import ResolverRegistry

F = TypeVar("F", bound=Callable[..., Any])


def list(  # noqa: A001 — intentional verb name; outside callers say `a2kit.list(...)`
    *,
    enricher: EnricherFn | None = None,
    store: ConnectionStore[Any] | None = None,
    connection: bool = True,
    connection_param: str | None = None,
    write: bool = False,
    streaming: bool = False,
    tool_call_guard: bool = True,
    otel: bool = True,
    tool_name: str | None = None,
    resolver_registry: ResolverRegistry | None = None,
    server: Any = None,
    capabilities: Iterable[Capability] = (),
    filter: ListViewMode | None = None,  # noqa: A002
    fields: ListViewMode | None = None,
    pagination: ListViewMode | None = None,
    router_context: Any = None,
    cli: str | None = None,
) -> Callable[[F], F]:
    """List-shaped tool. Defaults filter/fields/pagination to Local; adds Cap.READ."""
    caps = {Cap.READ, *capabilities}
    return tool(
        enricher=enricher,
        store=store,
        connection=connection,
        connection_param=connection_param,
        write=write,
        streaming=streaming,
        tool_call_guard=tool_call_guard,
        otel=otel,
        tool_name=tool_name,
        resolver_registry=resolver_registry,
        server=server,
        capabilities=caps,
        filter=Local if filter is None else filter,
        fields=Local if fields is None else fields,
        pagination=Local if pagination is None else pagination,
        router_context=router_context,
        cli=cli,
    )


def read(
    *,
    enricher: EnricherFn | None = None,
    store: ConnectionStore[Any] | None = None,
    connection: bool = True,
    connection_param: str | None = None,
    streaming: bool = False,
    tool_call_guard: bool = True,
    otel: bool = True,
    tool_name: str | None = None,
    resolver_registry: ResolverRegistry | None = None,
    server: Any = None,
    capabilities: Iterable[Capability] = (),
    filter: ListViewMode | None = None,  # noqa: A002
    fields: ListViewMode | None = None,
    pagination: ListViewMode | None = None,
    router_context: Any = None,
    cli: str | None = None,
) -> Callable[[F], F]:
    """Single-result-shaped tool. Tool body owns its own query/filter. Adds Cap.READ.

    No `write=` kwarg — read tools are read by definition; use `@a2kit.write`
    or `@a2kit.tool(write=True)` for mutation.
    """
    caps = {Cap.READ, *capabilities}
    return tool(
        enricher=enricher,
        store=store,
        connection=connection,
        connection_param=connection_param,
        write=False,
        streaming=streaming,
        tool_call_guard=tool_call_guard,
        otel=otel,
        tool_name=tool_name,
        resolver_registry=resolver_registry,
        server=server,
        capabilities=caps,
        filter=filter,
        fields=fields,
        pagination=pagination,
        router_context=router_context,
        cli=cli,
    )


def write(
    *,
    enricher: EnricherFn | None = None,
    store: ConnectionStore[Any] | None = None,
    connection: bool = True,
    connection_param: str | None = None,
    streaming: bool = False,
    tool_call_guard: bool = True,
    otel: bool = True,
    tool_name: str | None = None,
    resolver_registry: ResolverRegistry | None = None,
    server: Any = None,
    capabilities: Iterable[Capability] = (),
    filter: ListViewMode | None = None,  # noqa: A002
    fields: ListViewMode | None = None,
    pagination: ListViewMode | None = None,
    router_context: Any = None,
    cli: str | None = None,
) -> Callable[[F], F]:
    """Mutation-shaped tool. Sets `write=True` + adds Cap.WRITE.

    No list-view defaults — writes that want filter/fields/pagination opt in
    explicitly via the kwargs. (Most writes don't, e.g. `bulk_close(ids: list[str])`.)
    """
    caps = {Cap.WRITE, *capabilities}
    return tool(
        enricher=enricher,
        store=store,
        connection=connection,
        connection_param=connection_param,
        write=True,
        streaming=streaming,
        tool_call_guard=tool_call_guard,
        otel=otel,
        tool_name=tool_name,
        resolver_registry=resolver_registry,
        server=server,
        capabilities=caps,
        filter=filter,
        fields=fields,
        pagination=pagination,
        router_context=router_context,
        cli=cli,
    )


__all__ = ["list", "read", "write"]
