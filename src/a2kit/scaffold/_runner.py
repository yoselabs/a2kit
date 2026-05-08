"""MCPRunner + FastMCPLike + pyproject.toml loader.

Owns the runtime entry: argv parsing (`--scope`, `--select`, `--http`,
`--register`), router registry application, transport selection. Loads
`[tool.a2kit]` from the nearest pyproject.toml on init and registers any
declared capabilities so `default_select` can resolve them.
"""

from __future__ import annotations

import contextlib
import contextvars
import sys
import tomllib
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Protocol, runtime_checkable

from a2kit._capabilities import UnknownCapability, capabilities
from a2kit._select import (
    SelectExpr,
    default_select_expr,
    parse_select,
    validate_atoms,
)
from a2kit.scaffold._cli import _parse_multistore_register, register_ephemeral_connections

if TYPE_CHECKING:
    from a2kit.connections import ConnectionStore
    from a2kit.scaffold._routers import RouterRegistry


# Set by `MCPRunner._prepare` so the tool wrapper can resolve provider-bound
# kwonly params at call time without an explicit handle. The tool decorator
# checks this contextvar; when None, chained-DI auto-injection is silently
# skipped (the existing v0.11 connection injection still runs).
_CURRENT_RUNNER: contextvars.ContextVar[Any | None] = contextvars.ContextVar("a2kit_current_runner", default=None)


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
    """Register entries under `[tool.a2kit.capabilities]` into the global registry."""
    caps_table = a2kit_table.get("capabilities", {})
    if not caps_table:
        return
    if not isinstance(caps_table, dict):
        msg = "[tool.a2kit.capabilities] must be a table of name -> {description, aliases}"
        raise ValueError(msg)
    for name, body in caps_table.items():
        if not isinstance(body, dict):
            msg = f"Capability {name!r} body must be a table; got {type(body).__name__}"
            raise ValueError(msg)
        capabilities.register(
            name,
            description=body.get("description", ""),
            aliases=list(body.get("aliases", []) or []),
        )


@dataclass(frozen=True, slots=True)
class RunnerOptions:
    """Typed options for `MCPRunner.run(options=...)` — replaces argv-string
    round-tripping (v0.13).

    The Click `serve` subcommand constructs `RunnerOptions` directly from
    parsed flags, so MCP authors never round-trip through argv strings.

    `argv=` on `run()` / `run_async()` is kept as a compat layer for the
    v0.12 surface; new code should use `options=`.
    """

    http: str | None = None
    select_expr: str | None = None
    scope: str | None = None
    transport: Literal["stdio", "http"] | None = None
    registers: tuple[str, ...] = ()


@runtime_checkable
class FastMCPLike(Protocol):
    """Minimum FastMCP server surface a2kit drives.

    Any object passed to `MCPRunner(server, ...)` must satisfy this. The Protocol
    is intentionally loose: nested `settings` is `Any` because we only assign
    `settings.host` / `settings.port` at HTTP startup, and pinning the inner
    shape would reject test fakes for no real safety win.
    """

    settings: Any

    def tool(self, *args: Any, **kwargs: Any) -> Any: ...
    def run(self, *args: Any, **kwargs: Any) -> Any: ...


class MCPRunner:
    """Wraps `server.run()` to handle `--register`, `--scope`, `--select`, `--http`.

    `default_select` resolves in order: explicit kwarg →
    `[tool.a2kit.runner] default_select` in pyproject.toml → hard default
    `"default and not write and not destructive"`.

    pyproject.toml is walked up from CWD on init; `[tool.a2kit.capabilities]`
    entries are auto-registered.
    """

    def __init__(
        self,
        server: FastMCPLike,
        *,
        connection_store: ConnectionStore[Any] | None = None,
        router_registry: RouterRegistry | None = None,
        name: str = "a2kit",
        default_select: SelectExpr | str | None = None,
    ) -> None:
        self.server: FastMCPLike = server
        # v0.15: connection store is private; v0.12's `MCPRunner.store=`
        # public attribute is gone. App.connect() owns store lifecycle now.
        self._connection_store: ConnectionStore[Any] | None = connection_store
        self.router_registry = router_registry
        self.connection_class = connection_store.connection_class if connection_store is not None else None
        self.name = name

        a2kit_table = _load_pyproject_a2kit()
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
        with contextlib.suppress(Exception):
            validate_atoms(expr, known_routers=set(self.router_registry.names()), known_tools=set())
        include_writes = _expr_mentions(expr, "write") or _expr_mentions(expr, "destructive")
        self.router_registry.apply(self.server, self._connection_store, enabled=wanted, include_writes=include_writes)
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
        if self.router_registry is not None:
            stores_by_router = dict(self.router_registry.routers_with_stores(fallback_store=self._connection_store))
            distinct_stores = {id(s) for s in stores_by_router.values()}
            if len(distinct_stores) > 1:
                return _parse_multistore_register(parsed["register_args"], stores_by_router)
        if self._connection_store is None:
            return {}
        return register_ephemeral_connections(parsed["register_args"], store=self._connection_store)

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

    def _options_to_parsed(self, options: RunnerOptions) -> dict[str, Any]:
        """Convert typed `RunnerOptions` into the `_parse` dict shape.

        Bypasses argv round-tripping. Mirrors `_parse`'s output keys exactly
        so the rest of `_prepare` doesn't need to know which input shape was
        used.
        """
        register_args: list[str] = []
        for reg in options.registers:
            register_args.append("--register")
            # Each `--register` value is a string `"router:key field=val ..."`;
            # `_parse_multistore_register` / `register_ephemeral_connections`
            # tokenise on whitespace. Pre-split here so the downstream parser
            # sees the same token stream it would have received via argv.
            register_args.extend(reg.split())
        return {
            "scope": options.scope,
            "select": options.select_expr,
            "http": options.http,
            "register_args": register_args,
        }

    def _prepare(
        self,
        argv: list[str] | None,
        transport: str | None,
        *,
        options: RunnerOptions | None = None,
    ) -> tuple[dict[str, Any], str]:
        """Parse argv, register routers, decide transport. Pure-sync orchestration —
        shared by `run` (sync entry) and `run_async` (embedded entry).

        v0.15: provider/plugin DI is gone; resolution flows through
        Annotated[T, Depends(factory)] markers on tool kwonly params.
        """
        # Publish the runner so callers can find it during prepare(). Kept
        # for parity with the v0.12 contextvar; no auto-injection now.
        _CURRENT_RUNNER.set(self)

        if options is not None:
            parsed = self._options_to_parsed(options)
            if transport is None and options.transport is not None:
                transport = options.transport
        else:
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

    def run(
        self,
        argv: list[str] | None = None,
        *,
        transport: str | None = None,
        options: RunnerOptions | None = None,
    ) -> dict[str, Any]:
        """Parse argv, register routers, set transport seam, run the server.

        Pass `options=RunnerOptions(...)` (v0.13) to skip argv round-tripping;
        `argv=` stays as a compat layer.
        """
        from a2kit.tools import _set_current_transport  # noqa: PLC0415

        parsed, chosen = self._prepare(argv, transport, options=options)
        _set_current_transport(chosen)
        try:
            if chosen == "http":
                self.server.run(transport="streamable-http")
            else:
                self.server.run(transport="stdio")
        finally:
            _set_current_transport(None)
        return parsed

    async def run_async(
        self,
        argv: list[str] | None = None,
        *,
        transport: str | None = None,
        options: RunnerOptions | None = None,
    ) -> dict[str, Any]:
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

        parsed, chosen = self._prepare(argv, transport, options=options)
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
    "_CURRENT_RUNNER",
    "FastMCPLike",
    "MCPRunner",
    "RunnerOptions",
    "_atom_polarity",
    "_expr_mentions",
    "_find_pyproject",
    "_load_pyproject_a2kit",
    "_register_pyproject_capabilities",
]
