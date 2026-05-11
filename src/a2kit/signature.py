"""Signature helpers — protocol-neutral, domain-agnostic.

Tools are plain async functions. Their dependencies (factories, stores) are
held on the Router instance via constructor injection — there is no DI
sentinel for the framework to inspect.
"""

from __future__ import annotations

import inspect
import logging
from typing import TYPE_CHECKING, Any
from typing import get_type_hints as _stdlib_get_type_hints

if TYPE_CHECKING:
    from collections.abc import Callable

_log = logging.getLogger(__name__)
_WARN_ONCE: set[str] = set()


def resolve_hints(fn: Callable[..., Any]) -> dict[str, Any]:
    """Return type hints for ``fn`` or ``{}`` on any resolution failure.

    Single fallback policy for the five sites in core that previously rolled
    their own try/except. ``id(fn)``-based caching was tried and abandoned —
    Python recycles function ids across nested test scopes, producing stale
    cache hits. We rely on ``get_type_hints`` being fast enough at the warm
    path. On failure, logs a single WARN per fn name (deduped via
    ``__qualname__``) and returns ``{}``.
    """
    try:
        return _stdlib_get_type_hints(fn)
    except Exception as exc:
        name = getattr(fn, "__qualname__", getattr(fn, "__name__", "<callable>"))
        if name not in _WARN_ONCE:
            _WARN_ONCE.add(name)
            _log.warning("resolve_hints failed for %s: %s", name, exc)
        return {}


def _is_tool_context(ann: Any) -> bool:
    """Identity check for the ``a2kit.ToolContext`` annotation.

    Cold-start preserving: only consults ``sys.modules`` for ``fastmcp``. If
    fastmcp hasn't been imported in this process, the annotation cannot be
    ``fastmcp.Context`` (its class identity wouldn't exist), so we
    short-circuit. If fastmcp has been imported, identity-compare against
    ``fastmcp.Context``. The lazy ``a2kit.ToolContext`` re-export triggers
    fastmcp import only when a user accesses the symbol.
    """
    if ann is None or ann is inspect.Parameter.empty:
        return False
    import sys as _sys

    fastmcp_mod = _sys.modules.get("fastmcp")
    if fastmcp_mod is None:
        return False
    return ann is getattr(fastmcp_mod, "Context", None)


def find_context_param(fn: Callable[..., Any]) -> str | None:
    hints = resolve_hints(fn)
    for name, param in inspect.signature(fn).parameters.items():
        ann = hints.get(name, param.annotation)
        if _is_tool_context(ann):
            return name
    return None


_BOUND_FIRST = frozenset({"self", "cls"})


def user_input_params(fn: Callable[..., Any]) -> dict[str, inspect.Parameter]:
    ctx_name = find_context_param(fn)
    out: dict[str, inspect.Parameter] = {}
    for i, (name, param) in enumerate(inspect.signature(fn).parameters.items()):
        if i == 0 and name in _BOUND_FIRST:
            continue
        if name == ctx_name:
            continue
        out[name] = param
    return out


def wire_input_params(
    fn: Callable[..., Any],
    container: Any | None = None,
) -> tuple[dict[str, inspect.Parameter], set[str]]:
    """Return ``(wire_params, wire_scopes_needed)`` for ``fn``.

    Injectable kwargs (whose types match a registered container provider)
    are filtered out. ``wire_scopes_needed`` is the set of scope names
    (e.g. ``{"connection"}``) whose registered types appear in fn's
    parameter annotations. Callers (CLI/MCP schema gen) auto-synthesize
    one wire-side string param per scope. Core code is feature-name-free;
    the scope names come from the container (registered by consumer
    packages like ``a2kit.packages.connections``).
    """
    base = user_input_params(fn)
    if container is None:
        return base, set()
    hints = resolve_hints(fn)
    out: dict[str, inspect.Parameter] = {}
    for name, param in base.items():
        ann = hints.get(name, param.annotation)
        if container.has(ann):
            continue
        out[name] = param
    scopes_needed = container.wire_scopes_used_by(fn)
    # If the tool already declares a scope-name parameter itself (e.g. the
    # method takes ``connection: str`` directly), don't synthesize a duplicate.
    scopes_needed = {s for s in scopes_needed if s not in out}
    return out, scopes_needed
