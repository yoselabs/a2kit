from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from a2kit._context_protocol import ToolContext as ToolContext
    from a2kit.app import App
    from a2kit.exceptions import A2KitError
    from a2kit.routers import Router
    from a2kit.tool import list_, read, write


# Top-level re-exports. The 95% authoring surface only — introspection
# types (A2KitMeta, RouterRegistry, UNRESOLVED), non-umbrella exception
# subclasses, and sink-author types live in their owning modules and are
# importable from there directly.
_LAZY_ATTRS: dict[str, tuple[str, str]] = {
    "App": ("a2kit.app", "App"),
    "Router": ("a2kit.routers", "Router"),
    "read": ("a2kit.tool", "read"),
    "write": ("a2kit.tool", "write"),
    "list_": ("a2kit.tool", "list_"),
    "ToolContext": ("a2kit._context_protocol", "ToolContext"),
    "A2KitError": ("a2kit.exceptions", "A2KitError"),
    "HealthResult": ("a2kit.packages.health", "HealthResult"),
    "Principal": ("a2kit.packages.context", "Principal"),
}

_LAZY_MODULES: dict[str, str] = {
    "schema": "a2kit.schema",
}

# Removed-in-v0.33 symbols mapped to migration hints. Accessing any of these
# via `a2kit.<name>` raises AttributeError with a pointed message.
_REMOVED_IN_V033: dict[str, str] = {
    "tool": (
        "`@a2kit.tool` was removed in v0.33. Choose `@a2kit.read` (read-shaped), "
        "`@a2kit.write` (write-shaped), or `@a2kit.list_` (list-shaped) based on "
        "the tool's semantics."
    ),
}


def __getattr__(name: str) -> Any:
    from importlib import import_module

    mod_target = _LAZY_MODULES.get(name)
    if mod_target is not None:
        return import_module(mod_target)
    target = _LAZY_ATTRS.get(name)
    if target is None:
        hint = _REMOVED_IN_V033.get(name)
        if hint is not None:
            raise AttributeError(hint)
        raise AttributeError(f"module 'a2kit' has no attribute {name!r}")

    mod, attr = target
    return getattr(import_module(mod), attr)


def __dir__() -> list[str]:
    return sorted({*globals(), *_LAZY_ATTRS, *_LAZY_MODULES})


def run(app: App, argv: list[str] | None = None) -> Any:
    """Finisher: build the App's runtime and run its CLI.

    ``run`` is the production finisher. It builds an ``AppRuntime`` from
    the App internally (snapshotting the composition, validating the DI
    provider graph) before building and invoking the CLI — consumer code
    never calls a build step. See ADR 0019.
    """
    from a2kit.packages.cli import build_full_cli
    from a2kit.runtime import build

    runtime = build(app)
    cli = build_full_cli(runtime)
    return cli.main(args=argv, standalone_mode=True)


__all__ = [
    "A2KitError",
    "App",
    "HealthResult",
    "Router",
    "ToolContext",
    "list_",
    "read",
    "run",
    "write",
]
