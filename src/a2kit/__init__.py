from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastmcp import Context as ToolContext  # noqa: A2K-IMPORT-DISCIPLINE

    from a2kit.app import App
    from a2kit.capabilities import Cap, capabilities
    from a2kit.exceptions import (
        A2KitError,
        InvalidFilterExpression,
        InvalidToolReturnTypeError,
        ReportTypeMismatch,
        ReportTypeNotDeclared,
        ToolCallContamination,
    )
    from a2kit.metadata import A2KitMeta
    from a2kit.routers import Router, RouterRegistry
    from a2kit.surface import Surface
    from a2kit.tool import list_, read, tool, write


_LAZY_ATTRS: dict[str, tuple[str, str]] = {
    "App": ("a2kit.app", "App"),
    "UNRESOLVED": ("a2kit.app", "UNRESOLVED"),
    "Router": ("a2kit.routers", "Router"),
    "RouterRegistry": ("a2kit.routers", "RouterRegistry"),
    "Surface": ("a2kit.surface", "Surface"),
    "tool": ("a2kit.tool", "tool"),
    "read": ("a2kit.tool", "read"),
    "write": ("a2kit.tool", "write"),
    "list_": ("a2kit.tool", "list_"),
    "Cap": ("a2kit.capabilities", "Cap"),
    "capabilities": ("a2kit.capabilities", "capabilities"),
    "ToolContext": ("fastmcp", "Context"),
    "A2KitMeta": ("a2kit.metadata", "A2KitMeta"),
    "A2KitError": ("a2kit.exceptions", "A2KitError"),
    "ToolCallContamination": ("a2kit.exceptions", "ToolCallContamination"),
    "InvalidToolReturnTypeError": ("a2kit.exceptions", "InvalidToolReturnTypeError"),
    "InvalidFilterExpression": ("a2kit.exceptions", "InvalidFilterExpression"),
    "ReportTypeNotDeclared": ("a2kit.exceptions", "ReportTypeNotDeclared"),
    "ReportTypeMismatch": ("a2kit.exceptions", "ReportTypeMismatch"),
    "HealthResult": ("a2kit.packages.health", "HealthResult"),
}

_LAZY_MODULES: dict[str, str] = {
    "lifespan": "a2kit.lifespan",
}


def __getattr__(name: str) -> Any:
    from importlib import import_module

    mod_target = _LAZY_MODULES.get(name)
    if mod_target is not None:
        return import_module(mod_target)
    target = _LAZY_ATTRS.get(name)
    if target is None:
        raise AttributeError(f"module 'a2kit' has no attribute {name!r}")

    mod, attr = target
    return getattr(import_module(mod), attr)


def __dir__() -> list[str]:
    return sorted({*globals(), *_LAZY_ATTRS, *_LAZY_MODULES})


def run(app: App, argv: list[str] | None = None) -> Any:
    from a2kit.packages.cli.builder import build_full_cli

    cli = build_full_cli(app)
    return cli.main(args=argv, standalone_mode=True)


__all__ = [
    "UNRESOLVED",
    "A2KitError",
    "A2KitMeta",
    "App",
    "Cap",
    "HealthResult",
    "InvalidFilterExpression",
    "InvalidToolReturnTypeError",
    "ReportTypeMismatch",
    "ReportTypeNotDeclared",
    "Router",
    "RouterRegistry",
    "Surface",
    "ToolCallContamination",
    "ToolContext",
    "capabilities",
    "list_",
    "read",
    "run",
    "tool",
    "write",
]
