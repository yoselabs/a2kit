from __future__ import annotations

from typing import TYPE_CHECKING, Any

from a2kit._lazy_module import lazy_attr, lazy_dir

if TYPE_CHECKING:
    from a2kit._context_protocol import ToolContext as ToolContext
    from a2kit.app import App
    from a2kit.exceptions import A2KitError
    from a2kit.packages.di import Lazy
    from a2kit.packages.serve import ServeContext
    from a2kit.routers import Router
    from a2kit.tool import list_, read, write


# Top-level re-exports. The 95% authoring surface only — introspection
# types (A2KitMeta, RouterRegistry, UNRESOLVED), non-umbrella exception
# subclasses, and sink-author types live in their owning modules and are
# importable from there directly.
#
# Lazy[T] lives here because it's touched at the tool seam;
# a2kit.packages.* is documented as private scaffolding — top-level is the
# canonical path.
_LAZY_ATTRS: dict[str, tuple[str, str]] = {
    "App": ("a2kit.app", "App"),
    "Router": ("a2kit.routers", "Router"),
    "read": ("a2kit.tool", "read"),
    "write": ("a2kit.tool", "write"),
    "list_": ("a2kit.tool", "list_"),
    "enricher": ("a2kit.tool", "enricher"),
    "ToolContext": ("a2kit._context_protocol", "ToolContext"),
    "A2KitError": ("a2kit.exceptions", "A2KitError"),
    "HealthResult": ("a2kit.packages.health", "HealthResult"),
    "Principal": ("a2kit.packages.context", "Principal"),
    "Lazy": ("a2kit.packages.di", "Lazy"),
    "ServeContext": ("a2kit.packages.serve", "ServeContext"),
}

_LAZY_MODULES: dict[str, str] = {
    "schema": "a2kit.schema",
}

__getattr__ = lazy_attr(__name__, _LAZY_ATTRS, modules=_LAZY_MODULES)
__dir__ = lazy_dir(globals(), _LAZY_ATTRS, _LAZY_MODULES)
del lazy_attr, lazy_dir


def compose_default_surfaces() -> Any:
    """Compose the bundled MCP + HTTP surfaces and bind as the active registry.

    Per `bootstrap-surfaces-explicit` (2026-05-26): surfaces are no
    longer self-registered as import side effects. The facade (this
    function) composes the default surface set and binds it as the
    process's active registry so every `current_registry()` /
    `runtime.surfaces` reader sees a populated registry.

    Idempotent: if surfaces are already composed (e.g. on a second
    `compose_default_surfaces()` call within the same process) the
    existing registry is returned unchanged.

    The facade is the only layer-exempt module allowed to import L5
    surface packages from compose/finisher entry points without
    violating `A2K-LAYER`.

    Returns the active `SurfaceRegistry` for the caller to pass into
    `runtime.build(app, surfaces=...)`.
    """
    from a2kit.packages.dispatch.surface import (
        SurfaceRegistry,
        bind_active_registry,
        current_registry,
    )

    existing = current_registry()
    if existing is not None:
        return existing

    # Lazy substrate-package imports stay inside this function — cold-start
    # paths that never call `compose_default_surfaces()` (or `run()`) do
    # not pull fastmcp / fastapi.
    from a2kit.packages.http.api import ApiSurface
    from a2kit.packages.mcp.surface import McpSurface

    registry = SurfaceRegistry()
    registry.register_surface(McpSurface())
    registry.register_surface(ApiSurface())
    bind_active_registry(registry)
    return registry


def run(app: App, argv: list[str] | None = None) -> Any:
    """Finisher: build the App's runtime and run its CLI.

    ``run`` is the production finisher. It builds an ``AppRuntime`` from
    the App internally (snapshotting the composition, validating the DI
    provider graph) before building and invoking the CLI — consumer code
    never calls a build step. See ADR 0019.

    Composes the bundled surface set (see `compose_default_surfaces`)
    and passes it to `build()` so `expose=` validation runs against the
    composed registry per `bootstrap-surfaces-explicit`.
    """
    from a2kit.runtime import build

    surfaces = compose_default_surfaces()
    runtime = build(app, surfaces=surfaces)
    # The CLI is a LOCAL Surface (ADR 0028 Wave 1): materialize it through
    # the uniform bind(...) protocol rather than calling the builder free
    # function directly. CliSurface.bind owns the Typer build + vendored-
    # click guard.
    cli = app.cli.bind(runtime)
    return cli.main(args=argv, standalone_mode=True)


__all__ = [
    "A2KitError",
    "App",
    "HealthResult",
    "Lazy",
    "Router",
    "ServeContext",
    "ToolContext",
    "compose_default_surfaces",
    "enricher",
    "list_",
    "read",
    "run",
    "write",
]
