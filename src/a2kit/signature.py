from __future__ import annotations

import functools
import inspect
from typing import TYPE_CHECKING, Any, cast, get_type_hints

from uncalled_for import Depends, get_dependency_parameters, without_dependencies

from a2kit.metadata import get_meta, set_meta
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


def get_dependencies(fn: Callable[..., Any]) -> dict[str, Any]:
    return get_dependency_parameters(fn)


def strip_dependencies(fn: Callable[..., Any]) -> Callable[..., Any]:
    return without_dependencies(fn)


_BOUND_FIRST = frozenset({"self", "cls"})


def user_input_params(fn: Callable[..., Any]) -> dict[str, inspect.Parameter]:
    deps = set(get_dependencies(fn))
    ctx_name = find_context_param(fn)
    out: dict[str, inspect.Parameter] = {}
    for i, (name, param) in enumerate(inspect.signature(fn).parameters.items()):
        if i == 0 and name in _BOUND_FIRST:
            continue
        if name in deps or name == ctx_name:
            continue
        out[name] = param
    return out


def rebuild_with_factories(
    fn: Callable[..., Any],
    factories: dict[Callable[..., Any], Callable[..., Any]],
) -> Callable[..., Any]:
    """Return a function whose ``Depends(real)`` defaults are swapped per ``factories``.

    For each parameter whose default is a ``Depends`` instance pointing at a
    callable that is a key in ``factories``, replace the default with
    ``Depends(factories[real])``. The wrapper's ``__signature__`` carries the
    rewritten params so ``uncalled_for`` resolves the bound factory at call
    time. Metadata (``A2KitMeta``) is preserved.

    Returns ``fn`` unchanged if no parameter matches.
    """
    if not factories:
        return fn
    sig = inspect.signature(fn)
    new_params: list[inspect.Parameter] = []
    changed = False
    for param in sig.parameters.values():
        default = param.default
        factory = getattr(default, "factory", None)
        if factory is not None and factory in factories:
            new_params.append(param.replace(default=Depends(factories[factory])))
            changed = True
        else:
            new_params.append(param)
    if not changed:
        return fn

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return fn(*args, **kwargs)

    cast("Any", wrapper).__signature__ = sig.replace(parameters=new_params)
    meta = get_meta(fn)
    if meta is not None:
        set_meta(wrapper, meta)
    return wrapper
