"""Rewrite ``Annotated[T, pydantic.FieldInfo]`` -> ``Annotated[T, typer.Option]``.

Single internal helper consumed by :mod:`a2kit.packages.cli.builder`. Reads
``FieldInfo.description`` (set by tool authors via ``pydantic.Field(...)``)
and lifts it into ``typer.Option(help=...)`` so Typer renders it as the
CLI option's ``--help`` text. Other ``FieldInfo`` settings (validators,
constraints) are left untouched on the annotation; Typer doesn't honour
them but pydantic still validates downstream where the body model is
decoded.

If the annotation isn't ``Annotated``, returns it unchanged.
"""

from __future__ import annotations

from typing import Annotated, Any, get_args, get_origin

from pydantic.fields import FieldInfo


def field_to_typer_annotation(annotation: Any) -> Any:
    """Return ``annotation`` with FieldInfo metadata rewritten to ``typer.Option``.

    Always returns an ``Annotated[T, typer.Option(...)]`` wrapper so Typer
    renders the parameter as a ``--flag`` Option rather than a positional
    Argument. The ``help`` text is taken from ``FieldInfo.description`` when
    present.

    - ``Annotated[T, FieldInfo(description=...)]`` → ``Annotated[T, typer.Option(help=...)]``
    - ``Annotated[T, FieldInfo(...)]`` with no description → ``Annotated[T, typer.Option()]``
    - bare ``T`` → ``Annotated[T, typer.Option()]``
    - already-Annotated with non-FieldInfo metadata → returned unchanged.
    """
    import typer

    if get_origin(annotation) is None or not hasattr(annotation, "__metadata__"):
        return Annotated[annotation, typer.Option()]

    args = get_args(annotation)
    base = args[0]
    description: str | None = None
    has_field_info = False
    for meta in args[1:]:
        if isinstance(meta, FieldInfo):
            has_field_info = True
            if meta.description:
                description = meta.description
                break

    if description is not None:
        return Annotated[base, typer.Option(help=description)]
    if has_field_info:
        return Annotated[base, typer.Option()]
    return annotation
