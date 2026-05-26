"""Dispatch hook for connection-string resolution.

The connections package owns ``"connection"`` as a wire kwarg. Apps that
opt into connections install a dispatch hook that performs wire-side
conversion only:

1. Pulls ``connection: str`` out of wire kwargs (if present).
2. Awaits ``store.load(connection)`` to materialize the typed
   ``ConnectionConfig`` instance.
3. Surfaces the instance under the tool's parameter name (when the tool
   declares the config directly), or under a stable
   ``_a2k_seed_<TypeName>`` key (when the tool reaches the config
   through a chain) — either way the framework's ``Container.call_scope``
   wire-seeder picks it up by value type and registers it as a SCOPED
   provider on the per-call child container.

DI (provider chain resolution, ``Lazy[T]``, per-call lifecycle) is the
framework's job, run by ``Container.call_scope`` AFTER this hook on its
output. The container itself contains no reference to ``"connection"``.
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any

from a2kit.packages.di import Scope

if TYPE_CHECKING:
    from collections.abc import Callable

    from a2kit.packages.connections.config import ConnectionConfig
    from a2kit.packages.connections.store import ConnectionStore
    from a2kit.packages.di import Container


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
    """Build an async dispatch hook that resolves the wire ``connection`` string.

    The hook performs **wire-side conversion only**. It awaits the
    appropriate store's ``load`` to turn the wire ``connection`` string
    into typed ``ConnectionConfig`` instances and:

    1. Surfaces them as wire kwargs by tool-param name when the tool
       declares the config directly.
    2. Publishes them on the per-call DI child container via the
       explicit ``seed(type, value)`` callable so chain resolution from
       app-scope factories (e.g. Store → ConnectionConfig) finds the
       wire-resolved instance.

    DI itself is the framework's responsibility — run by
    ``Container.call_scope`` after this hook returns.

    ``stores`` maps each registered ConnectionConfig subclass to its
    store (built by :func:`install_connection_hook`).
    """

    async def hook(
        fn: Callable[..., Any],
        wire_kwargs: dict[str, Any],
        seed: Callable[[type, Any], None],
    ) -> dict[str, Any]:
        out = dict(wire_kwargs)
        conn = out.pop(_WIRE_CONN_KEY, None)
        if conn is not None:
            parts = tuple(p.strip() for p in conn.split(",")) if "," in conn else (conn,)
            for config_type, store in stores.items():
                if len(parts) == 1:
                    instance = await store.load(parts[0])
                else:
                    instance = await store.load(*parts)
                seed(config_type, instance)
                param_name = _fn_param_for_type(fn, config_type)
                if param_name is not None and param_name not in out:
                    out[param_name] = instance
        return out

    return hook


def install_connection_hook(
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
        if not container.has_provider(ct):
            # Register as a per-call (SCOPED) stub provider so chain
            # resolution routes through the call_scope child container,
            # where the hook-wired wire-seeder has registered the actual
            # typed instance. v0.36: connection configs are per-call by
            # nature — each dispatch can target a different connection.
            container.provide(ct, _stub_factory(ct), scope=Scope.SCOPED)
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


__all__ = ["install_connection_hook", "make_connection_hook"]
