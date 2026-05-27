"""Signature helpers — protocol-neutral, domain-agnostic.

Tools are plain async functions. Their dependencies (factories, stores) are
held on the Router instance via constructor injection — there is no DI
sentinel for the framework to inspect.
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any

# R2 (audit) — canonical resolve_hints lives in packages/di/_hints.py
# (the DI package is kept self-contained for standalone-shipping; see
# `di-scoped-lifecycle` design D9). signature.py at L2 imports L0
# cleanly via the package front door — no cycle, no layer violation.
from a2kit.packages.di import resolve_hints

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = [
    "find_context_param",
    "resolve_hints",
    "user_input_params",
    "wire_input_params",
]


def _is_tool_context(ann: Any) -> bool:
    """Identity check for the ``a2kit.ToolContext`` Protocol annotation.

    Primary path: match the a2kit-owned ``ToolContext`` Protocol. The Protocol
    lives in ``a2kit._context_protocol`` and is the canonical contract.

    Backward-compat path: consumers who annotated ``ctx: fastmcp.Context``
    directly (bypassing ``a2kit.ToolContext``) still match — when fastmcp
    is loaded, identity-compare against ``fastmcp.Context`` as a secondary
    check. Cold-start preserved: we only consult ``sys.modules`` for fastmcp,
    so a bare ``import a2kit`` still does not pull fastmcp.
    """
    if ann is None or ann is inspect.Parameter.empty:
        return False
    from a2kit._context_protocol import ToolContext as _ToolContextProto

    if ann is _ToolContextProto:
        return True
    import sys as _sys

    fastmcp_mod = _sys.modules.get("fastmcp")
    if fastmcp_mod is None:
        return False
    return ann is getattr(fastmcp_mod, "Context", None)


def _is_optional_tool_context(ann: Any) -> bool:
    """Detect ``Context | None`` / ``Optional[Context]`` / ``Union[Context, None]``.

    Returns ``True`` when the annotation is a Union/Optional whose members
    include both a ToolContext-shaped type (``a2kit.ToolContext`` Protocol or
    ``fastmcp.Context``) and ``NoneType``. Rejected by ``find_context_param``: the
    dispatcher always binds ``ctx`` when declared, so the Optional form is
    misleading typing with no runtime path producing ``None``.
    """
    if ann is None or ann is inspect.Parameter.empty:
        return False
    import types as _types
    import typing as _typing

    origin = _typing.get_origin(ann)
    if origin is _typing.Union or origin is _types.UnionType:
        args = _typing.get_args(ann)
        if type(None) in args and any(_is_tool_context(a) for a in args):
            return True
    return False


def find_context_param(fn: Callable[..., Any]) -> str | None:
    from a2kit.exceptions import A2KitInvalidContextAnnotation

    hints = resolve_hints(fn)
    for name, param in inspect.signature(fn).parameters.items():
        ann = hints.get(name, param.annotation)
        if _is_optional_tool_context(ann):
            raise A2KitInvalidContextAnnotation(
                fn_name=getattr(fn, "__qualname__", getattr(fn, "__name__", "<callable>")),
                param_name=name,
                hint=(
                    "ctx is always bound by the dispatcher when declared; "
                    "drop '| None' from the annotation, or remove ctx "
                    "entirely if the tool does not need it."
                ),
            )
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
    from a2kit.packages.di import lazy_inner_type as _lazy_inner_type

    base = user_input_params(fn)
    if container is None:
        return base, set()
    hints = resolve_hints(fn)
    out: dict[str, inspect.Parameter] = {}
    for name, param in base.items():
        ann = hints.get(name, param.annotation)
        if container.has_provider(ann):
            continue
        # Lazy[T] params are framework-injected closures, not wire-side.
        if _lazy_inner_type(ann) is not None:
            continue
        out[name] = param
    scopes_needed = container.wire_scopes_used_by(fn)
    # If the tool already declares a scope-name parameter itself (e.g. the
    # method takes ``connection: str`` directly), don't synthesize a duplicate.
    scopes_needed = {s for s in scopes_needed if s not in out}
    return out, scopes_needed
