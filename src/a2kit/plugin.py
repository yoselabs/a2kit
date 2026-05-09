"""``Plugin`` Protocol — extension contract for opt-in features.

Plugins extend an :class:`a2kit.App` with cross-cutting behavior:
- CLI subcommands (``cli_commands()``)
- MCP middleware (``mcp_middleware()``)
- ``Depends(<class>)`` resolvers (``depends_resolvers()``)
- Foreign-type registration via ``app.use(<thing>)`` (``claim``/``adopt``)

Plugins implement only what they contribute. The ``register(app)`` method
is the only required hook — everything else is duck-typed.

Concrete plugins live in ``a2kit.packages.*`` and are registered via
``app.use(SomePlugin())`` at the composition root.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from a2kit.app import App


@runtime_checkable
class Plugin(Protocol):
    """Minimum contract: a plugin knows how to register itself on an App.

    Optional (duck-typed) methods — plugins implement what they contribute:

    - ``cli_commands(self) -> list[click.Command]``
    - ``mcp_middleware(self) -> list[Any]``
    - ``depends_resolvers(self) -> list[DependsResolver]``
    - ``claim(self, thing: Any) -> bool``
    - ``adopt(self, thing: Any, app: App) -> None``
    """

    def register(self, app: App) -> None: ...


@runtime_checkable
class DependsResolver(Protocol):
    """Resolve ``Depends(<target>)`` defaults at tool-invocation time.

    The CLI / MCP builders walk ``app.depends_resolvers()`` to rewrite
    parameter defaults whose ``Depends(...)`` value points at something a
    resolver claims (typically a class — connection class, store class).
    """

    def claim(self, target: Any) -> bool: ...

    async def resolve(self, target: Any, kwargs: dict[str, Any], app: App) -> Any: ...


__all__ = ["DependsResolver", "Plugin"]
