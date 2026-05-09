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
