from __future__ import annotations

from typing import TYPE_CHECKING, Any

from a2kit.routers import Router, RouterRegistry
from a2kit.tool import ToolDescriptor, identity_dispatch_hook

if TYPE_CHECKING:
    from collections.abc import Callable

    import click


class App:
    """Composition root.

    Three named verbs: :meth:`add_router`, :meth:`add_cli`,
    :meth:`add_mcp_middleware`. No polymorphic dispatch, no plugin
    registry, no class-keyed DI in core. Routers are constructed with
    their dependencies via plain Python ``__init__`` and registered
    explicitly.

    Request-scoped DI is layered via :meth:`provide` — calling it once
    installs a non-identity dispatch hook from
    ``a2kit.packages.connections.container``. Apps that never call
    ``provide`` keep the identity hook and pay zero overhead.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self._routers = RouterRegistry()
        self._descriptors: list[ToolDescriptor] = []
        self._cli_extras: list[click.Command] = []
        self._mcp_middlewares: list[Any] = []
        # Lazy: created on first .provide() call.
        self._container: Any | None = None
        self._dispatch_hook: Callable[..., Any] = identity_dispatch_hook
        # LDD kill-switch — env A2KIT_LDD=off disables both channels at
        # startup; ``set_ldd(...)`` and CLI flags override per-invocation.
        import os

        env_off = os.environ.get("A2KIT_LDD", "").lower() == "off"
        self._ldd_reports = not env_off
        self._ldd_events = not env_off

    # --- Composition verbs ---------------------------------------------- #

    def add_router(self, router: Router) -> App:
        slug = router.slug
        existing = next((r for r in self._routers.all() if r.slug == slug), None)
        if existing is not None and existing is not router:
            msg = f"router slug {slug!r} already registered by {type(existing).__name__!r}; declare an explicit name= or rename the class"
            raise ValueError(msg)
        self._routers.add(router)
        self._descriptors.extend(_build_descriptors(router))
        return self

    def add_cli(self, command: click.Command) -> App:
        # Detect connections-cli markers and auto-register typed providers.
        types_marker = getattr(command, "_a2kit_connections_types", None)
        if types_marker:
            self._auto_register_connections(tuple(types_marker))
        self._cli_extras.append(command)
        return self

    def add_mcp_middleware(self, middleware: Any) -> App:
        self._mcp_middlewares.append(middleware)
        return self

    def cli_extras(self) -> list[click.Command]:
        return list(self._cli_extras)

    def mcp_middlewares(self) -> list[Any]:
        return list(self._mcp_middlewares)

    # --- DI: typed providers ------------------------------------------- #

    def provide(
        self,
        type_: type,
        factory: Callable[..., Any] | None = None,
    ) -> App:
        """Register a typed provider for ``type_``.

        When ``factory`` is omitted, the class itself is the factory and
        the container introspects ``type_.__init__`` at resolve time.
        """
        self._ensure_container()
        container: Any = self._container
        container.register(type_, factory)
        return self

    def has_provider(self, type_: type) -> bool:
        if self._container is None:
            return False
        return self._container.has(type_)

    def container(self) -> Any | None:
        return self._container

    def dispatch_hook(self) -> Callable[..., Any]:
        return self._dispatch_hook

    # --- LDD kill-switch ------------------------------------------------ #

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

    # --- Router / tool aggregation -------------------------------------- #

    def routers(self) -> list[Router]:
        return self._routers.all()

    def tools(self) -> list[Callable[..., Any]]:
        return self._routers.tools()

    def tool_descriptors(self) -> list[ToolDescriptor]:
        """Typed descriptors materialized at ``add_router`` time. One per tool.

        Each descriptor carries the resolved return type and the pre-computed
        ``format_hint`` so the CLI runtime can dispatch encoders without
        re-running type inference per call.
        """
        return list(self._descriptors)

    # --- internals ----------------------------------------------------- #

    def _ensure_container(self) -> None:
        if self._container is not None:
            return
        from a2kit.packages.connections.container import Container, container_dispatch

        self._container = Container()
        container = self._container

        async def _hook(fn: Callable[..., Any], wire_kwargs: dict[str, Any]) -> dict[str, Any]:
            return await container_dispatch(fn, wire_kwargs, container)

        self._dispatch_hook = _hook

    def _auto_register_connections(self, conn_types: tuple[type, ...]) -> None:
        """Delegate to the connections package's typed-provider installer."""
        from a2kit.packages.connections.container import install_connection_providers

        self._ensure_container()
        container: Any = self._container
        install_connection_providers(container, conn_types)


def _build_descriptors(router: Router) -> list[ToolDescriptor]:
    """Materialize one ``ToolDescriptor`` per tool on ``router``.

    Resolves return-type annotations (handling ``from __future__ import
    annotations`` and string-quoted forward refs) and computes each tool's
    ``format_hint`` via ``infer_format_hint``. On any resolution failure, the
    descriptor falls back to ``return_type=None`` and ``format_hint="json"``
    and a warning is logged once per tool.
    """
    import logging
    import typing

    from a2kit.packages.formatter.inference import infer_format_hint

    log = logging.getLogger(__name__)
    out: list[ToolDescriptor] = []
    for fn in router.tools():
        try:
            hints = typing.get_type_hints(fn, include_extras=True)
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "Failed to resolve type hints for %s.%s: %s",
                router.slug,
                getattr(fn, "__name__", "<callable>"),
                exc,
            )
            hints = {}
        return_type = hints.get("return")
        format_hint = infer_format_hint(return_type)
        out.append(
            ToolDescriptor(
                name=getattr(fn, "__name__", "<callable>"),
                router=router,
                fn=fn,
                return_type=return_type,
                format_hint=format_hint,
            )
        )
    return out
