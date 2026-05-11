"""Dispatch hook for connection-string resolution.

The connections package owns ``"connection"`` as a wire kwarg. Apps that
opt into connections install a dispatch hook that runs BEFORE the container
resolves typed dependencies:

1. Pulls ``connection: str`` out of wire kwargs (if present).
2. Awaits ``store.load(connection)`` to materialize the typed
   ``ConnectionConfig`` instance.
3. Substitutes the instance into wire kwargs under the parameter name the
   tool method expects.
4. Hands off to ``container.apply_kwargs(fn, wire_kwargs)`` synchronously
   for the rest of DI.

The container itself contains no reference to ``"connection"``. The magic
name lives in this file (and the consumer's own config / store) — nowhere
else in a2kit.
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    from a2kit.packages.connections.config import ConnectionConfig
    from a2kit.packages.connections.store import ConnectionStore
    from a2kit.packages.di.container import Container


_WIRE_CONN_KEY = "connection"


def _fn_param_for_type(fn: Callable[..., Any], target_type: type) -> str | None:
    """Return the name of fn's parameter whose annotation matches ``target_type``."""
    from a2kit.signature import resolve_hints

    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return None
    hints = resolve_hints(fn)
    for pname, param in sig.parameters.items():
        if pname == "self":
            continue
        ann = hints.get(pname, param.annotation)
        if ann is target_type:
            return pname
    return None


def make_connection_hook(
    container: Container,
    stores: dict[type, ConnectionStore[Any]],
) -> Callable[..., Any]:
    """Build an async dispatch hook that resolves ``connection`` before DI runs.

    ``stores`` maps each registered ConnectionConfig subclass to its store
    (built by :func:`install_connection_dispatch`). The hook awaits the
    appropriate store's ``load`` when a tool's parameter is one of the
    registered config types.
    """

    async def hook(fn: Callable[..., Any], wire_kwargs: dict[str, Any]) -> dict[str, Any]:
        conn = wire_kwargs.pop(_WIRE_CONN_KEY, None)
        pre_resolved: dict[type, Any] = {}
        if conn is not None:
            parts = tuple(p.strip() for p in conn.split(",")) if "," in conn else (conn,)
            for config_type, store in stores.items():
                if len(parts) == 1:
                    pre_resolved[config_type] = await store.load(parts[0])
                else:
                    pre_resolved[config_type] = await store.load(*parts)
                # If the tool method itself takes the config directly (no chain),
                # also surface it as a direct wire kwarg.
                param_name = _fn_param_for_type(fn, config_type)
                if param_name is not None and param_name not in wire_kwargs:
                    wire_kwargs[param_name] = pre_resolved[config_type]
        return container.apply_kwargs(fn, wire_kwargs, pre_resolved=pre_resolved)

    return hook


def install_connection_dispatch(
    app: Any,
    conn_types: tuple[type[ConnectionConfig], ...],
) -> None:
    """Wire ``app._dispatch_hook`` to the connection-aware async hook.

    Called from the ``connections(*types)`` Router's ``install``. Three
    things happen:

    1. Each ``conn_type`` is registered as the ``"connection"`` wire scope
       on the container. Schema gen sees this and synthesizes a wire-side
       ``connection: str`` param for any tool taking one of these types.
    2. Each ``conn_type`` is registered as a no-op provider so
       ``container.has(T)`` returns True (lets schema gen filter T from the
       user-facing wire surface). The factory raises if ever called — the
       hook substitutes the resolved value before the container resolves.
    3. ``app._dispatch_hook`` is replaced with the async connection-aware
       hook that awaits ``store.load`` and substitutes typed configs into
       wire kwargs.
    """
    from a2kit.packages.connections.store import ConnectionStore

    stores: dict[type, ConnectionStore[Any]] = {ct: ConnectionStore(ct) for ct in conn_types}
    container = app._container  # noqa: SLF001
    container.register_wire_scope(_WIRE_CONN_KEY, *conn_types)
    for ct in conn_types:
        if not container.has(ct):
            container.register(ct, _stub_factory(ct))
    app._dispatch_hook = make_connection_hook(container, stores)  # noqa: SLF001


def _stub_factory(ct: type) -> Callable[..., Any]:
    """No-op provider for a connection type. The dispatch hook substitutes
    the resolved value before the container ever calls this; reaching here
    means something installed the connections plumbing without wiring the
    dispatch hook.
    """

    def _stub() -> Any:
        msg = (
            f"connection type {ct!r} reached the container's factory path; "
            "the connections dispatch hook should have substituted the value "
            "into wire kwargs before the container resolved it. Did the hook "
            "get overwritten?"
        )
        raise RuntimeError(msg)

    _stub.__name__ = f"_stub_{ct.__name__}"
    return _stub


__all__ = ["install_connection_dispatch", "make_connection_hook"]
