"""AST helpers shared across lint rule modules.

Resolves R9 from the 2026-05-27 structural audit — small AST checks
that were re-rolled across multiple rule files. Each helper here has
exactly one home.
"""

from __future__ import annotations

import ast


def is_basemodel_base(base: ast.expr) -> bool:
    """Return True if ``base`` looks like ``BaseModel`` or ``pydantic.BaseModel``.

    Handles three shapes:
    - bare name: ``BaseModel``
    - dotted attribute: ``pydantic.BaseModel``
    - subscripted generic carrier: ``BaseModel[T]`` / ``Page[T]``
      (recurses into ``.value`` — a ``Page(BaseModel, Generic[T])``
      subclass still resolves)

    R9 superset of the two previous local copies in
    ``no_dict_str_any.py`` and ``local_return_model.py``.
    """
    if isinstance(base, ast.Name):
        return base.id == "BaseModel"
    if isinstance(base, ast.Attribute):
        return base.attr == "BaseModel"
    if isinstance(base, ast.Subscript):
        return is_basemodel_base(base.value)
    return False


__all__ = ["is_basemodel_base"]
