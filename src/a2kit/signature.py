"""Signature helpers — protocol-neutral, domain-agnostic.

Tools are plain async functions. Their dependencies (factories, stores) are
held on the Router instance via constructor injection — there is no DI
sentinel for the framework to inspect.
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any, get_type_hints

from a2kit.runtime import ToolContext

if TYPE_CHECKING:
    from collections.abc import Callable


def find_context_param(fn: Callable[..., Any]) -> str | None:
    try:
        hints = get_type_hints(fn)
    except Exception:
        hints = {}
    for name, param in inspect.signature(fn).parameters.items():
        ann = hints.get(name, param.annotation)
        if ann is ToolContext:
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
) -> tuple[dict[str, inspect.Parameter], bool]:
    """Return ``(wire_params, needs_connection)`` for ``fn``.

    Injectable kwargs (whose types match a registered container provider)
    are filtered out. ``needs_connection`` is True when at least one
    injectable's chain reaches a ``connection: str`` boundary; callers
    (CLI/MCP schema gen) auto-add a wire ``connection: str`` option.
    """
    base = user_input_params(fn)
    if container is None:
        return base, False
    try:
        hints = get_type_hints(fn)
    except Exception:
        hints = {}
    out: dict[str, inspect.Parameter] = {}
    needs_conn = False
    for name, param in base.items():
        ann = hints.get(name, param.annotation)
        if container.has(ann):
            if container._chain_reaches_connection(ann):  # noqa: SLF001
                needs_conn = True
            continue
        out[name] = param
    # If a tool method already declares ``connection: str`` itself, it's
    # already in ``out``; needs_conn stays False from this loop and we
    # don't synthesize a duplicate.
    if "connection" in out:
        needs_conn = False
    return out, needs_conn
