from __future__ import annotations

from typing import TYPE_CHECKING, Any

from a2kit.routers import Router, RouterRegistry

if TYPE_CHECKING:
    from collections.abc import Callable

    import click

    from a2kit.plugin import DependsResolver, Plugin


class App:
    """Composition root.

    Core knows about routers, plugins, and the LDD kill-switch — nothing
    else. Domain features (connections, etc.) plug in via :class:`Plugin`
    and ``app.use(SomePlugin())``.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self._routers = RouterRegistry()
        self._plugins: list[Plugin] = []
        # Generic Depends-factory override map (used by tests + multi-tenant
        # patterns; not domain-specific). `app.use_factory(real, as_=stub)`
        # swaps `Depends(stub)` → `Depends(real)` at tool-collection time.
        self._factories: dict[Callable[..., Any], Callable[..., Any]] = {}
        # LDD kill-switch — env A2KIT_LDD=off disables both channels at
        # startup; ``set_ldd(...)`` and CLI flags override per-invocation.
        import os

        env_off = os.environ.get("A2KIT_LDD", "").lower() == "off"
        self._ldd_reports = not env_off
        self._ldd_events = not env_off

    # --- Polymorphic registration ---------------------------------------- #

    def use(self, thing: Any) -> App:
        """Register a Router instance, a Plugin instance, or a foreign type
        (typically a class) that some registered plugin claims.

        Dispatch order:
        1. Class → foreign type, walk plugins for ``claim``/``adopt``.
        2. Router instance → core-native registry.
        3. Plugin instance (has ``register(app)`` method) → register + stash.
        """
        # Classes are foreign types — let a plugin claim. Doing this BEFORE
        # the Plugin Protocol check avoids ABCMeta's `register()` method
        # false-matching the Plugin protocol on Pydantic config classes.
        if isinstance(thing, type):
            for plugin in self._plugins:
                claim = getattr(plugin, "claim", None)
                adopt = getattr(plugin, "adopt", None)
                if callable(claim) and callable(adopt) and claim(thing):
                    adopt(thing, self)
                    return self
            plugins_str = ", ".join(type(p).__name__ for p in self._plugins) or "(none)"
            msg = (
                f"app.use({thing.__name__}): no plugin claims this class. "
                f"Registered plugins: [{plugins_str}]. "
                "Did you forget `app.use(SomePlugin())` first?"
            )
            raise TypeError(msg)
        # Router instance — core-native.
        if isinstance(thing, Router):
            self._routers.add(thing)
            return self
        # Plugin instance — duck-type register(app).
        register_method = getattr(thing, "register", None)
        if callable(register_method):
            register_method(self)
            self._plugins.append(thing)
            return self
        msg = (
            f"app.use({thing!r}): expected a Plugin instance, Router instance, "
            f"or a class claimed by a registered plugin. Got {type(thing).__name__}."
        )
        raise TypeError(msg)

    def use_factory(
        self,
        factory: Callable[..., Any],
        *,
        as_: Callable[..., Any],
    ) -> App:
        """Bind ``factory`` under the stable callable identity ``as_``.

        Tools declaring ``Depends(as_)`` resolve through ``factory`` at
        invocation. Generic — works for any callable identity, not just
        connections.
        """
        self._factories[as_] = factory
        return self

    def factories(self) -> dict[Callable[..., Any], Callable[..., Any]]:
        return dict(self._factories)

    # --- Backwards-compat sugar (delegates to claim/adopt) -------------- #

    def connect(self, conn_class: type) -> App:
        """Legacy alias — forwards to whichever plugin claims ``conn_class``.

        Prefer ``app.use(conn_class)`` after ``app.use(<plugin>)``.
        """
        for plugin in self._plugins:
            claim = getattr(plugin, "claim", None)
            adopt = getattr(plugin, "adopt", None)
            if callable(claim) and callable(adopt) and claim(conn_class):
                adopt(conn_class, self)
                return self
        plugins_str = ", ".join(type(p).__name__ for p in self._plugins) or "(none)"
        msg = (
            f"App.connect({conn_class.__name__}): no plugin claims this class. "
            f"Did you forget `app.use(Connections())`? Registered plugins: [{plugins_str}]."
        )
        raise RuntimeError(msg)

    # --- LDD kill-switch ------------------------------------------------- #

    def set_ldd(self, *, reports: bool | None = None, events: bool | None = None) -> App:
        if reports is not None:
            self._ldd_reports = reports
        if events is not None:
            self._ldd_events = events
        return self

    @property
    def ldd_reports(self) -> bool:
        return self._ldd_reports

    @property
    def ldd_events(self) -> bool:
        return self._ldd_events

    # --- Plugin contribution accessors ---------------------------------- #

    def plugins(self) -> list[Plugin]:
        return list(self._plugins)

    def cli_commands(self) -> list[click.Command]:
        out: list[click.Command] = []
        for plugin in self._plugins:
            method = getattr(plugin, "cli_commands", None)
            if callable(method):
                out.extend(method())
        return out

    def mcp_middlewares(self) -> list[Any]:
        out: list[Any] = []
        for plugin in self._plugins:
            method = getattr(plugin, "mcp_middleware", None)
            if callable(method):
                out.extend(method())
        return out

    def depends_resolvers(self) -> list[DependsResolver]:
        out: list[DependsResolver] = []
        for plugin in self._plugins:
            method = getattr(plugin, "depends_resolvers", None)
            if callable(method):
                out.extend(method())
        return out

    # --- Router / tool aggregation -------------------------------------- #

    def routers(self) -> list[Router]:
        return self._routers.all()

    def tools(self) -> list[Callable[..., Any]]:
        from a2kit.signature import bind_class_dependencies, rebuild_with_factories

        raw = self._routers.tools()
        # 1. generic factory-override pass (legacy `use_factory(...)`).
        if self._factories:
            raw = [rebuild_with_factories(fn, self._factories) for fn in raw]
        # 2. class-Depends resolution. Always run — when there are no
        #    resolvers, this still raises if the tool body has class-Depends
        #    defaults (which would otherwise sit unresolved).
        return [bind_class_dependencies(fn, self) for fn in raw]
