"""Tool capability computation, metadata stamping, doc injection, server registration.

This is the post-call-time stuff that gets baked into the wrapper at
decoration time and read back later by the runner / lint / consumers via
`tool_metadata(fn)`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from a2kit._capabilities import Cap, Capability

if TYPE_CHECKING:
    import inspect

    from a2kit.formatter import FormatName


def _compute_tool_capabilities(author: set[Capability], *, write: bool, tool_name: str) -> set[Capability]:
    """Auto-tag seam: union author caps + write/router context.

    Reads the active router (set by `RouterRegistry.apply()` via
    `a2kit._router_state._set_active`). Adds:
      - `Cap.READ` or `Cap.WRITE` (router phase or `write=True` flag)
      - active router name (if `router.auto_tag=True`) and `router.capabilities`
      - `tool:<resolved_tool_name>` for tool-namespace selection
      - `default` when the tool is on a default router (or has no router)
    """
    from a2kit._router_state import _get_active  # noqa: PLC0415

    caps: set[Capability] = set(author)
    if write:
        caps.add(Cap.WRITE)
    active = _get_active()
    if active is not None:
        caps.update(active.router.capabilities)
        if active.router.auto_tag:  # pragma: no branch — auto_tag=False routers don't surface in standard test apply paths
            caps.add(active.router.name)
            caps.add(f"router:{active.router.name}")
        if active.phase == "read":  # pragma: no branch — write phase is exercised under apply with include_writes
            caps.add(Cap.READ)
        elif active.phase == "write":  # pragma: no branch — apply always sets phase to read or write
            caps.add(Cap.WRITE)
        if active.router.default:  # pragma: no branch — default=False routers exit early via _wanted_routers filtering
            caps.add("default")
    else:
        caps.add("default")
    caps.add(f"tool:{tool_name}")
    return caps


def _inject_param_docs(
    wrapper: Any,
    fn: Any,
    sig: inspect.Signature,
    *,
    connection_param: str | None = None,
    cli: str | None = None,
    available_connections: list[str] | None = None,
) -> None:
    """Auto-inject canonical param-doc text into the function's docstring.

    Two sources, in order:

    1. If `connection_param` is set, prepend the canonical
       `connection_param_doc(...)` text for it.
    2. For any other registered param doc (`register_param_doc(name, text)`),
       append `f"{name}: {text}"`.

    Skips additions for params already mentioned in the existing docstring —
    explicit author text always wins.

    Configurable: `[tool.a2kit.docs] auto_inject = false` disables entirely.
    """
    if not _auto_inject_enabled():
        return
    from a2kit.docs import _registered_param_docs, connection_param_doc  # noqa: PLC0415

    registry = _registered_param_docs()
    existing = wrapper.__doc__ or ""
    additions: list[str] = []
    effective_sig = getattr(wrapper, "__signature__", None) or sig
    for param_name in effective_sig.parameters:
        if param_name in existing:
            continue
        if param_name == connection_param:
            additions.append(
                connection_param_doc(
                    param_name,
                    cli=cli or "a2kit",
                    available=available_connections,
                )
            )
        elif param_name in registry:
            additions.append(f"{param_name}: {registry[param_name]}")
    if not additions:
        return
    suffix = "\n\n" + "\n".join(additions)
    new_doc = (existing.rstrip() + suffix) if existing else "\n".join(additions)
    wrapper.__doc__ = new_doc
    fn.__doc__ = new_doc


_AUTO_INJECT_CACHE: dict[str, bool] = {}


def _auto_inject_enabled() -> bool:
    """Read `[tool.a2kit.docs] auto_inject` from pyproject.toml. Default True."""
    if "value" in _AUTO_INJECT_CACHE:
        return _AUTO_INJECT_CACHE["value"]
    value = True
    try:
        from a2kit.scaffold import _load_pyproject_a2kit  # noqa: PLC0415

        table = _load_pyproject_a2kit().get("docs", {})
        if isinstance(table, dict) and "auto_inject" in table:
            value = bool(table["auto_inject"])
    except Exception:  # noqa: BLE001 — defensive; never break the decorator
        value = True
    _AUTO_INJECT_CACHE["value"] = value
    return value


def _reset_auto_inject_cache() -> None:
    """Test seam — drop the cached pyproject value."""
    _AUTO_INJECT_CACHE.clear()


def _register_with_server(server: Any, wrapper: Any, name: str) -> None:
    """Register `wrapper` with a FastMCP server idempotently.

    If a tool with the same name (and same callable) is already registered, skip.
    Otherwise call `server.tool()(wrapper)`.
    """
    try:
        existing = server._tool_manager.list_tools()  # noqa: SLF001
    except AttributeError:  # pragma: no cover — defensive against test fakes lacking _tool_manager
        existing = []
    for entry in existing:
        if getattr(entry, "name", None) == name:  # pragma: no cover — idempotent re-registration is exercised in real apps
            return
    server.tool()(wrapper)


@dataclass(frozen=True, slots=True)
class ToolMetadata:
    """Public read-only view of `@a2kit.tool`-stamped attributes on a wrapper.

    Returned by :func:`tool_metadata`. The shape is the contract; the underlying
    `_a2kit_*` attributes are the implementation. Tests and consumers should
    assert against `ToolMetadata`, not the raw attrs.
    """

    capabilities: frozenset[Any]
    tool_name: str
    format: FormatName | None


def tool_metadata(fn: Any) -> ToolMetadata:
    """Return the kit-stamped metadata for a `@a2kit.tool`-decorated function.

    Raises ``AttributeError`` if `fn` was not decorated with the kit (i.e. the
    `_a2kit_tool_name` stamp is missing). Stable across releases — the
    underlying private attrs may change shape, the return value won't.
    """
    try:
        tool_name = fn._a2kit_tool_name  # noqa: SLF001
    except AttributeError as exc:  # pragma: no cover — defensive
        msg = f"{getattr(fn, '__name__', fn)!r} is not decorated with @a2kit.tool"
        raise AttributeError(msg) from exc
    raw_caps = getattr(fn, "_a2kit_capabilities", set())
    return ToolMetadata(
        capabilities=frozenset(raw_caps),
        tool_name=tool_name,
        format=getattr(fn, "_a2kit_format", None),
    )


__all__ = [
    "ToolMetadata",
    "_auto_inject_enabled",
    "_compute_tool_capabilities",
    "_inject_param_docs",
    "_register_with_server",
    "_reset_auto_inject_cache",
    "tool_metadata",
]
