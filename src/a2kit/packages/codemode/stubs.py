"""Monty type-stub generation from tool descriptors — dataclass mirrors + per-tool ``call_tool`` overloads."""

from __future__ import annotations

import types
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from typing import Any, Literal, Union, get_args, get_origin
from uuid import UUID

from pydantic import BaseModel

from .marshal import collect_models, dataclass_mirror

_SCALAR_NAMES: dict[type, str] = {int: "int", float: "float", bool: "bool", str: "str"}
# Types that ``model_dump(mode="json")`` renders as a string.
_AS_STRING: tuple[type, ...] = (datetime, date, time, UUID, Decimal)


def _annotation_str(annotation: Any) -> str:  # noqa: C901, PLR0911, PLR0912 -- a flat type-shape dispatch; splitting it would not read clearer
    """Render an annotation as monty-type-checkable stub text.

    Stays within the subset the spike proved monty handles: scalars,
    ``None``, ``list[...]``, ``dict``, ``X | Y`` unions, the generated
    dataclass mirror names, and ``Any`` as the safe fallback.
    """
    if annotation is None or annotation is type(None):
        return "None"
    if annotation is Any:
        return "Any"
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return dataclass_mirror(annotation).__name__
    if isinstance(annotation, type):
        if annotation in _SCALAR_NAMES:
            return _SCALAR_NAMES[annotation]
        if annotation in _AS_STRING or issubclass(annotation, Enum):
            return "str"
        if annotation in (list, tuple):
            return "list[Any]"
        if annotation is dict:
            return "dict"
        return "Any"

    origin = get_origin(annotation)
    if origin in (list, tuple):
        args = get_args(annotation)
        inner = _annotation_str(args[0]) if args and args[0] is not Ellipsis else "Any"
        return f"list[{inner}]"
    if origin is dict:
        return "dict"
    if origin is Union or isinstance(annotation, types.UnionType):
        parts: list[str] = []
        for arg in get_args(annotation):
            rendered = _annotation_str(arg)
            if rendered not in parts:
                parts.append(rendered)
        return " | ".join(parts) if parts else "Any"
    if origin is Literal:
        return "Any"
    return "Any"


def generate_stubs(tools: list[tuple[str, Any]]) -> str:
    """Build the monty ``type_check_stubs`` text for ``tools``
    (``[(name, return_type), ...]``): a dataclass mirror per reachable model
    plus one ``Literal``-keyed ``call_tool`` ``@overload`` per tool.
    """
    models: list[type] = []
    for _, return_type in tools:
        collect_models(return_type, models)

    lines = [
        "from dataclasses import dataclass",
        "from typing import Any, Literal, overload",
        "",
    ]
    for model in models:
        mirror = dataclass_mirror(model)
        lines.append("@dataclass")
        lines.append(f"class {mirror.__name__}:")
        fields = getattr(model, "model_fields", {})
        if not fields:
            lines.append("    pass")
        for fname, field in fields.items():
            lines.append(f"    {fname}: {_annotation_str(field.annotation)}")
        lines.append("")

    for name, return_type in tools:
        lines.append("@overload")
        lines.append(f"async def call_tool(name: Literal[{name!r}], params: dict) -> {_annotation_str(return_type)}: ...")
    lines.append("async def call_tool(name: str, params: dict) -> Any: ...")
    return "\n".join(lines) + "\n"


__all__ = ["generate_stubs"]
