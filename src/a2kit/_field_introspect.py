"""Internal helper: extract description from ``Annotated[T, pydantic.Field(...)]``.

a2kit reads pydantic ``FieldInfo`` metadata to forward parameter descriptions
to the MCP input schema and CLI option help. Tool authors write
``Annotated[T, pydantic.Field(description="...")]`` directly — there is no
a2kit-specific wrapper. This module is the introspection seam.
"""

from __future__ import annotations

from typing import Any


def description_of(annotation: Any) -> str | None:
    """Extract the ``description`` from an ``Annotated[T, Field(...)]`` annotation.

    Returns ``None`` when the annotation isn't ``Annotated`` or carries no
    pydantic ``FieldInfo`` metadata.
    """
    import typing

    args = typing.get_args(annotation)
    if not args:
        return None
    for meta in args[1:]:
        desc = getattr(meta, "description", None)
        if isinstance(desc, str):
            return desc
    return None


__all__ = ["description_of"]
