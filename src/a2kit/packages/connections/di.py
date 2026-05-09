"""Class-based DI resolvers contributed by the ``Connections`` plugin.

Two resolvers:

- :class:`ConnDependsResolver` — claims subclasses of
  :class:`ConnectionConfig` (registered on the plugin); resolves to the
  loaded conn for the user-supplied ``connection: str`` kwarg.
- :class:`StoreDependsResolver` — claims classes whose ``conn_type``
  attribute or ``Store[ConnT]`` Generic parameter is a registered
  connection class; resolves to ``StoreT(loaded_conn)``.

The previous core-level helper ``a2kit.signature.bind_class_dependencies``
walks plugin-contributed resolvers; this module supplies the connection
side.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from a2kit.packages.connections.exceptions import (
    ConnectionNotRegistered,
    StoreConnectionTypeUnknown,
)
from a2kit.packages.connections.factory import get_conn_factory
from a2kit.packages.connections.store_marker import store_conn_type

if TYPE_CHECKING:
    from a2kit.app import App
    from a2kit.packages.connections.config import ConnectionConfig
    from a2kit.packages.connections.plugin import Connections


class ConnDependsResolver:
    """Resolves ``Depends(ConnT)`` where ``ConnT`` is a ``ConnectionConfig`` subclass.

    Claims any ``ConnectionConfig`` subclass — registered or not. If not
    registered, ``resolve(...)`` raises :class:`ConnectionNotRegistered`
    so the user gets a precise diagnostic at decoration time.
    """

    def __init__(self, plugin: Connections) -> None:
        self._plugin = plugin

    def claim(self, target: Any) -> bool:
        from a2kit.packages.connections.config import ConnectionConfig

        return isinstance(target, type) and issubclass(target, ConnectionConfig)

    def precheck(self, target: type, _app: App) -> None:
        """Decoration-time validation — fails fast if conn isn't registered."""
        if target not in self._plugin.conn_types():
            raise ConnectionNotRegistered(target)

    async def resolve(self, target: Any, kwargs: dict[str, Any], app: App) -> Any:
        if target not in self._plugin.conn_types():
            raise ConnectionNotRegistered(target)
        connection = kwargs.get("connection")
        factory = get_conn_factory(app, target)
        return await factory(connection=connection)


class StoreDependsResolver:
    """Resolves ``Depends(StoreT)`` where ``StoreT`` declares its conn type.

    Claims any class whose ``conn_type`` attribute or ``Store[ConnT]``
    Generic parameter resolves; if the conn type isn't registered, raises
    :class:`ConnectionNotRegistered`. If neither marker is present the
    class is NOT claimed (some other plugin might handle it).
    """

    def __init__(self, plugin: Connections) -> None:
        self._plugin = plugin

    def claim(self, target: Any) -> bool:
        if not isinstance(target, type):
            return False
        return store_conn_type(target) is not None

    def precheck(self, target: type, _app: App) -> None:
        conn_type = store_conn_type(target)
        if conn_type is None:
            raise StoreConnectionTypeUnknown(target)
        if conn_type not in self._plugin.conn_types():
            raise ConnectionNotRegistered(conn_type)

    async def resolve(self, target: Any, kwargs: dict[str, Any], app: App) -> Any:
        conn_type = store_conn_type(target)
        if conn_type is None:
            raise StoreConnectionTypeUnknown(target)
        if conn_type not in self._plugin.conn_types():
            raise ConnectionNotRegistered(conn_type)
        connection = kwargs.get("connection")
        factory = get_conn_factory(app, cast("type[ConnectionConfig]", conn_type))
        conn = await factory(connection=connection)
        return target(conn)


__all__ = ["ConnDependsResolver", "StoreDependsResolver"]
