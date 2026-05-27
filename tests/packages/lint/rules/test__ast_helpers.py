"""Mirror tests for packages/lint/rules/_ast_helpers — shared AST checks."""

from __future__ import annotations

import ast

from a2kit.packages.lint.rules._ast_helpers import is_basemodel_base


def _expr(src: str) -> ast.expr:
    """Parse a single Python expression to an ast.expr."""
    return ast.parse(src, mode="eval").body


def test_bare_basemodel_name():
    assert is_basemodel_base(_expr("BaseModel")) is True


def test_dotted_basemodel_attribute():
    assert is_basemodel_base(_expr("pydantic.BaseModel")) is True


def test_subscripted_generic_carrier_recurses():
    assert is_basemodel_base(_expr("BaseModel[T]")) is True
    assert is_basemodel_base(_expr("Page[T]")) is False


def test_non_basemodel_names_reject():
    assert is_basemodel_base(_expr("object")) is False
    assert is_basemodel_base(_expr("dict")) is False


def test_arbitrary_expr_rejects():
    # not Name / Attribute / Subscript
    assert is_basemodel_base(_expr("'BaseModel'")) is False
