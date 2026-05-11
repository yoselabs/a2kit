"""``a2kit.Param`` — annotation marker for tool kwarg metadata.

Round-2 a2web feedback (item 9): consumers want a way to attach descriptions
(and other schema metadata) to tool kwargs that are direct parameters
(not Pydantic body models). Pydantic's ``Field(description=...)`` already
covers the body-model case via ``Annotated[T, Field(...)]``; ``Param`` is the
sibling for direct kwargs.

``Param`` is a thin wrapper that returns a ``pydantic.Field`` info object
underneath, so:

- The MCP input schema picks up the description automatically (FastMCP
  delegates to pydantic which honors ``Annotated`` metadata).
- The CLI builder reads the description and forwards it to click's
  ``--option HELP`` string.

Usage::

    from typing import Annotated
    import a2kit

    @a2kit.read()
    async def fetch(*, url: Annotated[str, a2kit.Param(description="Absolute http(s) URL.")]) -> dict:
        ...
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pydantic.fields import FieldInfo


def Param(description: str | None = None, **extras: Any) -> FieldInfo:  # noqa: N802 — public marker, idiomatic capitalized
    """Build a Pydantic ``FieldInfo`` carrying tool-kwarg metadata.

    Two call shapes:

    - **Positional shorthand**: ``Param("Absolute URL.")``. Cosmetically shorter
      at the ``Annotated[T, Param(...)]`` call site.
    - **Keyword form**: ``Param(description="Absolute URL.")``. Equivalent.

    Passing both raises ``TypeError`` (Python's natural "got multiple values
    for argument 'description'"); the message mentions ``description`` so test
    assertions on it stay simple.

    Both forms accept ``extras`` forwarded to ``pydantic.Field`` (``examples=``,
    ``title=``, ``ge=``, ``le=``).
    """
    from pydantic import Field

    return Field(description=description, **extras)


def description_of(annotation: Any) -> str | None:
    """Extract the ``description`` from an ``Annotated[T, Param(...)]`` annotation.

    Returns ``None`` when the annotation isn't ``Annotated`` or carries no
    pydantic ``FieldInfo`` metadata.
    """
    import typing

    args = typing.get_args(annotation)
    if not args:
        return None
    for meta in args[1:]:
        # pydantic FieldInfo has a ``description`` attribute.
        desc = getattr(meta, "description", None)
        if isinstance(desc, str):
            return desc
    return None


__all__ = ["Param", "description_of"]
