from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from a2kit.app import App
    from a2kit.capabilities import Cap, capabilities
    from a2kit.exceptions import (
        A2KitError,
        InvalidFilterExpression,
        InvalidToolReturnTypeError,
        ReportTypeMismatch,
        ReportTypeNotDeclared,
        ToolCallContamination,
        WriteNotAllowed,
    )
    from a2kit.metadata import A2KitMeta, ListViewSettings
    from a2kit.routers import Router, RouterRegistry
    from a2kit.runtime import ToolContext
    from a2kit.store import Store
    from a2kit.tool import list_, read, tool, write


_LAZY_ATTRS: dict[str, tuple[str, str]] = {
    "App": ("a2kit.app", "App"),
    "Router": ("a2kit.routers", "Router"),
    "RouterRegistry": ("a2kit.routers", "RouterRegistry"),
    "tool": ("a2kit.tool", "tool"),
    "read": ("a2kit.tool", "read"),
    "write": ("a2kit.tool", "write"),
    "list_": ("a2kit.tool", "list_"),
    "Cap": ("a2kit.capabilities", "Cap"),
    "capabilities": ("a2kit.capabilities", "capabilities"),
    "Store": ("a2kit.store", "Store"),
    "ToolContext": ("a2kit.runtime", "ToolContext"),
    "A2KitMeta": ("a2kit.metadata", "A2KitMeta"),
    "ListViewSettings": ("a2kit.metadata", "ListViewSettings"),
    "A2KitError": ("a2kit.exceptions", "A2KitError"),
    "ToolCallContamination": ("a2kit.exceptions", "ToolCallContamination"),
    "InvalidToolReturnTypeError": ("a2kit.exceptions", "InvalidToolReturnTypeError"),
    "WriteNotAllowed": ("a2kit.exceptions", "WriteNotAllowed"),
    "InvalidFilterExpression": ("a2kit.exceptions", "InvalidFilterExpression"),
    "ReportTypeNotDeclared": ("a2kit.exceptions", "ReportTypeNotDeclared"),
    "ReportTypeMismatch": ("a2kit.exceptions", "ReportTypeMismatch"),
    "ConnectionKwargMissing": ("a2kit.exceptions", "ConnectionKwargMissing"),
    "ConnectionNotRegistered": ("a2kit.exceptions", "ConnectionNotRegistered"),
    "StoreConnectionTypeUnknown": ("a2kit.exceptions", "StoreConnectionTypeUnknown"),
}


def __getattr__(name: str) -> Any:
    target = _LAZY_ATTRS.get(name)
    if target is None:
        raise AttributeError(f"module 'a2kit' has no attribute {name!r}")
    from importlib import import_module

    mod, attr = target
    return getattr(import_module(mod), attr)


def __dir__() -> list[str]:
    return sorted({*globals(), *_LAZY_ATTRS})


def run(app: App, argv: list[str] | None = None) -> Any:
    from a2kit.packages.cli.builder import build_full_cli

    cli = build_full_cli(app)
    return cli.main(args=argv, standalone_mode=True)


__all__ = [
    "A2KitError",
    "A2KitMeta",
    "App",
    "Cap",
    "ConnectionKwargMissing",
    "ConnectionNotRegistered",
    "InvalidFilterExpression",
    "InvalidToolReturnTypeError",
    "ListViewSettings",
    "ReportTypeMismatch",
    "ReportTypeNotDeclared",
    "Router",
    "RouterRegistry",
    "Store",
    "StoreConnectionTypeUnknown",
    "ToolCallContamination",
    "ToolContext",
    "WriteNotAllowed",
    "capabilities",
    "list_",
    "read",
    "run",
    "tool",
    "write",
]
