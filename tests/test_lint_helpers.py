"""Cover edge paths in a2kit.lint._ast_helpers + remaining gaps in static/runtime/tools."""

from __future__ import annotations

import ast

from a2kit.lint._ast_helpers import (
    decorator_kwargs,
    is_a2kit_tool_decorator,
    is_server_tool_decorator,
    is_tool_function,
    local_pydantic_classes,
)


def test_is_a2kit_tool_decorator_unknown_call() -> None:
    tree = ast.parse("@something.weird()\ndef f(): pass\n")
    func = tree.body[0]
    assert is_a2kit_tool_decorator(func.decorator_list[0]) is False


def test_is_a2kit_tool_decorator_bare_call() -> None:
    tree = ast.parse("@some_unknown_name\ndef f(): pass\n")
    func = tree.body[0]
    assert is_a2kit_tool_decorator(func.decorator_list[0]) is False


def test_is_a2kit_tool_decorator_attribute_no_parens() -> None:
    """Decorator written without parens — `@a2kit.tool` (still recognised)."""
    tree = ast.parse("@a2kit.tool\ndef f(): pass\n")
    func = tree.body[0]
    assert is_a2kit_tool_decorator(func.decorator_list[0]) is True


def test_decorator_kwargs_no_call() -> None:
    """Plain Name (no call) → returns empty dict."""
    name = ast.Name(id="foo", ctx=ast.Load())
    assert decorator_kwargs(name) == {}


def test_is_server_tool_decorator_attribute_no_parens() -> None:
    tree = ast.parse("@server.tool\ndef f(): pass\n")
    func = tree.body[0]
    assert is_server_tool_decorator(func.decorator_list[0]) is True


def test_is_tool_function_skips_non_function() -> None:
    tree = ast.parse("x = 1\n")
    assert is_tool_function(tree.body[0]) is False


def test_local_pydantic_classes_attribute_base() -> None:
    code = "class C(pydantic.BaseModel): pass\n"
    tree = ast.parse(code)
    assert "C" in local_pydantic_classes(tree)


def test_local_pydantic_classes_unrelated_base() -> None:
    code = "class C(object): pass\n"
    tree = ast.parse(code)
    assert local_pydantic_classes(tree) == set()


def test_is_a2kit_tool_decorator_other_name() -> None:
    """Bare Name decorator that isn't 'tool' returns False."""
    tree = ast.parse("@some_other\ndef f(): pass\n")
    func = tree.body[0]
    assert is_a2kit_tool_decorator(func.decorator_list[0]) is False


def test_is_a2kit_tool_decorator_subscript_target_falls_through() -> None:
    """Decorator whose call.func is a Subscript (neither Attribute nor Name) returns False."""
    code = "@deco[0]()\ndef f(): pass\n"
    tree = ast.parse(code)
    func = tree.body[0]
    assert is_a2kit_tool_decorator(func.decorator_list[0]) is False
