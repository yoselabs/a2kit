"""Cover edge paths in a2kit.lint._ast_helpers + remaining gaps in static/runtime/tools."""

from __future__ import annotations

import ast

from a2kit.lint._ast_helpers import (
    connection_info_subclasses,
    decorator_kwargs,
    is_a2kit_tool_decorator,
    is_server_tool_decorator,
    is_tool_function,
    key_fields_value,
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


def test_connection_info_subclasses_attribute_base() -> None:
    code = "class C(a2kit.ConnectionInfo): pass\n"
    tree = ast.parse(code)
    classes = list(connection_info_subclasses(tree))
    assert len(classes) == 1


def test_connection_info_subclasses_skips_non_class() -> None:
    code = "x = 1\nclass D: pass\n"
    tree = ast.parse(code)
    assert list(connection_info_subclasses(tree)) == []


def test_connection_info_subclasses_non_module() -> None:
    """Helper handles non-Module input gracefully."""
    expr = ast.parse("x", mode="eval")
    assert list(connection_info_subclasses(expr)) == []


def test_key_fields_value_returns_none_when_absent() -> None:
    cls = ast.parse("class C: pass\n").body[0]
    assert key_fields_value(cls) is None


def test_key_fields_value_skips_non_name_target() -> None:
    """Tuple-targeted assignment shouldn't match KEY_FIELDS."""
    cls = ast.parse("class C:\n    a, KEY_FIELDS = 1, ('x',)\n").body[0]
    # The `Name` 'KEY_FIELDS' inside a Tuple target IS still a Name; verify the
    # helper doesn't mis-match on the outer Tuple wrapper.
    val = key_fields_value(cls)
    # We accept either: helper currently iterates `targets` directly, so for
    # `a, KEY_FIELDS = ...` the target is a Tuple — `t.id == "KEY_FIELDS"` is False.
    assert val is None


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


def test_connection_info_subclasses_via_name() -> None:
    """`class C(ConnectionInfo)` (bare Name base) is recognised."""
    code = "class C(ConnectionInfo): pass\n"
    tree = ast.parse(code)
    classes = list(connection_info_subclasses(tree))
    assert len(classes) == 1


def test_connection_info_subclasses_unrelated_base() -> None:
    code = "class C(object): pass\n"
    tree = ast.parse(code)
    assert list(connection_info_subclasses(tree)) == []


def test_connection_info_subclasses_with_subscript_base() -> None:
    """Generic-style base like `Foo[Bar]` (a Subscript) is neither Attribute nor Name."""
    code = "class C(Generic[X], ConnectionInfo): pass\n"
    tree = ast.parse(code)
    classes = list(connection_info_subclasses(tree))
    assert len(classes) == 1


def test_is_a2kit_tool_decorator_subscript_target_falls_through() -> None:
    """Decorator whose call.func is a Subscript (neither Attribute nor Name) returns False."""
    # `@deco[0]()` — odd but valid AST; covers the `return False` line.
    code = "@deco[0]()\ndef f(): pass\n"
    tree = ast.parse(code)
    func = tree.body[0]
    assert is_a2kit_tool_decorator(func.decorator_list[0]) is False
