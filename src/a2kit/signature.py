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


def _is_registered_conn(target: Any, app: Any) -> bool:
    return isinstance(target, type) and target in getattr(app, "_connection_types", [])


async def _resolve_conn_for(conn_type: type, app: Any, connection: Any) -> Any:
    from a2kit.exceptions import ConnectionNotRegistered
    from a2kit.packages.connections.config import ConnectionConfig
    from a2kit.packages.connections.factory import get_conn_factory

    if not _is_registered_conn(conn_type, app):
        raise ConnectionNotRegistered(conn_type)
    if not issubclass(conn_type, ConnectionConfig):
        raise ConnectionNotRegistered(conn_type)
    factory = get_conn_factory(app, conn_type)
    return await factory(connection=connection)


async def _resolve_store_for(store_type: type, app: Any, connection: Any) -> Any:
    from a2kit.exceptions import StoreConnectionTypeUnknown
    from a2kit.store import store_conn_type

    conn_type = store_conn_type(store_type)
    if conn_type is None:
        raise StoreConnectionTypeUnknown(store_type)
    conn = await _resolve_conn_for(conn_type, app, connection)
    return store_type(conn)


def bind_class_dependencies(fn: Callable[..., Any], app: Any) -> Callable[..., Any]:  # noqa: C901
    """Resolve ``Depends(<class>)`` defaults via an outer wrapper.

    For each parameter whose default is ``Depends(<class>)`` where the class
    is a registered connection or a store with a known conn binding, drop
    that parameter from the wrapper's signature and resolve it at call time
    using the user-supplied ``connection`` kwarg.

    The wrapper hides class-Depends params (they're auto-injected). Other
    ``Depends(callable)`` defaults are preserved — uncalled_for handles them
    via the existing factory path. Plain user kwargs are unchanged.

    Returns ``fn`` unchanged when no class-Depends is present. Preserves
    :class:`A2KitMeta`.
    """
    from a2kit.exceptions import ConnectionNotRegistered, StoreConnectionTypeUnknown
    from a2kit.store import store_conn_type as _sct

    sig = inspect.signature(fn)
    class_injections: list[tuple[str, type, str]] = []  # (name, target_class, "conn"|"store")
    kept_params: list[inspect.Parameter] = []

    for param in sig.parameters.values():
        default = param.default
        target = getattr(default, "factory", None)
        if isinstance(target, type):
            if _is_registered_conn(target, app):
                class_injections.append((param.name, target, "conn"))
                continue
            if _sct(target) is not None:
                class_injections.append((param.name, target, "store"))
                continue
            from a2kit.packages.connections.config import ConnectionConfig

            if issubclass(target, ConnectionConfig):
                raise ConnectionNotRegistered(target)
            raise StoreConnectionTypeUnknown(target)
        kept_params.append(param)

    if not class_injections:
        return fn

    is_async = inspect.iscoroutinefunction(fn)

    if is_async:

        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            connection = kwargs.get("connection")
            for name, target_class, kind in class_injections:
                if kind == "conn":
                    kwargs[name] = await _resolve_conn_for(target_class, app, connection)
                else:
                    kwargs[name] = await _resolve_store_for(target_class, app, connection)
            return await fn(*args, **kwargs)
    else:

        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:  # type: ignore[no-redef]
            connection = kwargs.get("connection")
            for name, target_class, kind in class_injections:
                if kind == "conn":
                    kwargs[name] = await _resolve_conn_for(target_class, app, connection)
                else:
                    kwargs[name] = await _resolve_store_for(target_class, app, connection)
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
