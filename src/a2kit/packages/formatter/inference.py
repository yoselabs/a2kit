"""Type-driven format-hint inference for ``ToolDescriptor``.

Given a tool's resolved return-type annotation, ``infer_format_hint`` returns
``"tsv" | "json" | "page-tsv"`` deterministically. JSON is the safe default
for any input the inference can't positively prove tabular — missing
annotations, ``Any``, ``Union`` shapes, unresolved forward refs, etc.

The module is a leaf: imports only stdlib + pydantic + ``response`` (for
``Page``). No imports from ``cli`` / ``runtime`` — the formatter package is
the lowest layer.
"""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from typing import Any, Literal, Union, get_args, get_origin
from uuid import UUID

from pydantic import BaseModel

from .response import Page

FormatHintInferred = Literal["tsv", "json", "page-tsv"]

_DUMP_SCALAR_TYPES: tuple[type, ...] = (
    str,
    int,
    float,
    bool,
    bytes,
    datetime,
    date,
    time,
    Decimal,
    UUID,
)


def _is_basemodel(tp: Any) -> bool:
    return isinstance(tp, type) and issubclass(tp, BaseModel)


def _is_dump_scalar(annotation: Any) -> bool:  # noqa: PLR0911
    """Return True iff ``annotation`` (or its inner type after unwrapping
    ``Optional`` / ``Annotated`` / ``Literal``) is a type that
    ``BaseModel.model_dump(mode="json")`` produces as a primitive scalar.
    """
    if annotation is None or annotation is type(None):
        return True

    origin = get_origin(annotation)

    # Annotated[T, ...] — unwrap to T
    if origin is not None and getattr(annotation, "__metadata__", None) is not None:
        # typing.Annotated unwrap: first arg is the underlying type
        return _is_dump_scalar(get_args(annotation)[0])

    # Literal[...] — every literal value is a scalar by construction
    if origin is Literal:
        return True

    # Union[...] / Optional[...] — every branch must be scalar
    if origin is Union or _is_pep604_union(annotation):
        return all(_is_dump_scalar(a) for a in get_args(annotation))

    # Bare type — direct membership or Enum subclass
    if isinstance(annotation, type):
        if annotation in _DUMP_SCALAR_TYPES:
            return True
        return issubclass(annotation, Enum)

    # Parameterized generics (list[str], dict[...], tuple[...]) → not scalar
    return False


def _is_pep604_union(annotation: Any) -> bool:
    # ``str | None`` produces ``types.UnionType``, distinct from typing.Union.
    import types

    return isinstance(annotation, types.UnionType)


def _model_is_scalar_only(cls: type[BaseModel]) -> bool:
    return all(_is_dump_scalar(field.annotation) for field in cls.model_fields.values())


def infer_format_hint(return_type: Any) -> FormatHintInferred:  # noqa: PLR0911
    """Map a resolved return-type annotation to a wire-format hint.

    Defaults to ``"json"`` whenever the type is missing, ambiguous, or not
    positively provable as tabular.
    """
    if return_type is None or return_type is Any:
        return "json"

    origin = get_origin(return_type)

    # Page[T] (or subclass) — hybrid envelope
    if origin is None and isinstance(return_type, type) and issubclass(return_type, Page):
        # bare ``Page`` (no parameter) or subclass without parameterization on
        # the call site — inspect the class's __pydantic_generic_metadata__ for
        # the resolved item type.
        item_type = _page_item_type(return_type)
        if item_type is not None and _is_basemodel(item_type) and _model_is_scalar_only(item_type):
            return "page-tsv"
        return "json"

    if origin is not None and isinstance(origin, type) and issubclass(origin, Page):
        args = get_args(return_type)
        if len(args) == 1 and _is_basemodel(args[0]) and _model_is_scalar_only(args[0]):
            return "page-tsv"
        return "json"

    # list[T] / tuple[T] — TSV when T is scalar-only BaseModel
    if origin in (list, tuple):
        args = get_args(return_type)
        # tuple[X, ...] is variable-length; tuple[X, Y] is fixed and not TSV-able
        if origin is tuple:
            if len(args) == 2 and args[1] is Ellipsis:
                args = (args[0],)
            else:
                return "json"
        if len(args) == 1 and _is_basemodel(args[0]) and _model_is_scalar_only(args[0]):
            return "tsv"
        return "json"

    # Everything else (single BaseModel, dict, scalars, Union, Optional) → JSON
    return "json"


def _page_item_type(cls: type[Page]) -> Any | None:
    """Extract the bound item type from a Page subclass declared as
    ``class SearchPage(Page[Task])``. Returns None if Page is bare.

    Pydantic resolves the type variable into ``model_fields["items"].annotation``
    as ``list[Task]`` even when ``__pydantic_generic_metadata__`` is empty for
    a concrete subclass, so we read it off the field.
    """
    items_field = cls.model_fields.get("items")
    if items_field is None:
        return None
    items_ann = items_field.annotation
    if get_origin(items_ann) is list:
        args = get_args(items_ann)
        # Reject the bare TypeVar case (still T, not bound) — a typing.TypeVar
        # has no `mro`, so isinstance(args[0], type) is False.
        if len(args) == 1 and isinstance(args[0], type):
            return args[0]
    return None
