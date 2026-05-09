"""Signature helpers — protocol-neutral, domain-agnostic.

Class-based ``Depends(<class>)`` resolution flows through plugin-contributed
:class:`a2kit.plugin.DependsResolver` instances. Core has no knowledge of
specific class shapes (e.g. :class:`ConnectionConfig`). Plugins
(``Connections``, etc.) own their resolvers and contribute them via
``app.depends_resolvers()``.
"""

from __future__ import annotations

import functools
import inspect
from typing import TYPE_CHECKING, Any, cast, get_type_hints

from uncalled_for import Depends, get_dependency_parameters, without_dependencies

from a2kit.metadata import get_meta, set_meta
from a2kit.runtime import ToolContext

if TYPE_CHECKING:
    from collections.abc import Callable

    from a2kit.app import App


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


def bind_class_dependencies(fn: Callable[..., Any], app: App) -> Callable[..., Any]:  # noqa: C901
    """Resolve ``Depends(<class>)`` defaults via plugin-contributed resolvers.

    For each parameter whose default is ``Depends(<class>)``, walk
    ``app.depends_resolvers()`` to find one whose ``claim(target)`` returns
    True. Drop that parameter from the wrapper's signature and resolve it at
    call time via the resolver's ``resolve(target, kwargs, app)`` coroutine.

    Class-Depends defaults that no resolver claims raise ``TypeError`` at
    decoration time — the App is missing a plugin.

    Returns ``fn`` unchanged when no class-Depends is present. Preserves
    :class:`A2KitMeta`.
    """
    sig = inspect.signature(fn)
    resolvers = app.depends_resolvers()
    class_injections: list[tuple[str, type, Any]] = []  # (name, target_class, resolver)
    kept_params: list[inspect.Parameter] = []

    for param in sig.parameters.values():
        default = param.default
        target = getattr(default, "factory", None)
        if isinstance(target, type):
            chosen = next((r for r in resolvers if r.claim(target)), None)
            if chosen is None:
                plugin_names = ", ".join(type(p).__name__ for p in app.plugins()) or "(none)"
                msg = (
                    f"`Depends({target.__name__})` is not handled by any registered plugin. "
                    f"Did you forget `app.use(<SomePlugin>)`? Active plugins: [{plugin_names}]."
                )
                raise TypeError(msg)
            # Optional decoration-time precheck — resolvers raise here if
            # they "claim" the target but can't actually resolve it
            # (e.g. ConnectionConfig subclass not registered yet).
            precheck = getattr(chosen, "precheck", None)
            if callable(precheck):
                precheck(target, app)
            class_injections.append((param.name, target, chosen))
            continue
        kept_params.append(param)

    if not class_injections:
        return fn

    is_async = inspect.iscoroutinefunction(fn)

    if is_async:

        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            for name, target_class, resolver in class_injections:
                kwargs[name] = await resolver.resolve(target_class, kwargs, app)
            return await fn(*args, **kwargs)
    else:

        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:  # type: ignore[no-redef]
            for name, target_class, resolver in class_injections:
                kwargs[name] = await resolver.resolve(target_class, kwargs, app)
            return fn(*args, **kwargs)

    cast("Any", wrapper).__signature__ = sig.replace(parameters=kept_params)
    hidden = {n for n, _, _ in class_injections}
    wrapper.__annotations__ = {k: v for k, v in fn.__annotations__.items() if k not in hidden}
    meta = get_meta(fn)
    if meta is not None:
        set_meta(wrapper, meta)
    return wrapper


def rebuild_with_factories(
    fn: Callable[..., Any],
    factories: dict[Callable[..., Any], Callable[..., Any]],
) -> Callable[..., Any]:
    """Return a function whose ``Depends(real)`` defaults are swapped per ``factories``.

    Backwards-compat helper for the legacy ``app.use_factory(...)`` flow,
    which moved out of core. Kept here for direct callers (e.g. test
    overrides via ``a2kit.packages.testing.make_test_app``).

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
