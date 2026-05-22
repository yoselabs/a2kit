"""Tests for `a2kit.packages.lint.rules.detect` — shared AST-shape helpers."""

from __future__ import annotations


def test_decorator_helpers_recognize_bare_write_name() -> None:
    """`@write` (Name form) is recognized — covers `is_a2kit_tool_decorator` Name branch."""
    import ast

    from a2kit.packages.lint.rules.detect import is_a2kit_tool_decorator, is_server_tool_decorator, is_tool_function

    src = "@write\ndef f():\n    pass\n"
    tree = ast.parse(src)
    fn = tree.body[0]
    dec = fn.decorator_list[0]  # ty: ignore[unresolved-attribute]  # why: stub object exposes attributes only at runtime; static checker can't see them
    assert is_a2kit_tool_decorator(dec) is True
    # `@write` is a Name (not Attribute) — server detector returns False.
    assert is_server_tool_decorator(dec) is False
    assert is_tool_function(fn) is True


def test_decorator_helpers_recognize_server_tool_attr() -> None:
    """`@server.tool()` (Attribute form, non-a2kit) — only server detector returns True."""
    import ast

    from a2kit.packages.lint.rules.detect import is_a2kit_tool_decorator, is_server_tool_decorator

    src = "@server.tool()\ndef f():\n    pass\n"
    tree = ast.parse(src)
    fn = tree.body[0]
    dec = fn.decorator_list[0]  # ty: ignore[unresolved-attribute]  # why: stub object exposes attributes only at runtime; static checker can't see them
    # is_a2kit_tool_decorator: target.value is a Name 'server' not in {'a2kit', 'tools'} → False
    assert is_a2kit_tool_decorator(dec) is False
    assert is_server_tool_decorator(dec) is True


def test_decorator_helpers_unknown_decorator_returns_false() -> None:
    import ast

    from a2kit.packages.lint.rules.detect import is_a2kit_tool_decorator, is_server_tool_decorator

    src = "@somemod.somemethod\ndef f():\n    pass\n"
    tree = ast.parse(src)
    dec = tree.body[0].decorator_list[0]  # ty: ignore[unresolved-attribute]  # why: stub object exposes attributes only at runtime; static checker can't see them
    assert is_a2kit_tool_decorator(dec) is False
    # The Attribute is `somemod.somemethod` (attr != 'tool') → server detector also False
    assert is_server_tool_decorator(dec) is False


def test_decorator_helpers_constant_decorator_returns_false() -> None:
    """`@(some_factory())()` Call where target is itself a Call (not Name/Attribute) → False."""
    import ast

    from a2kit.packages.lint.rules.detect import is_a2kit_tool_decorator, is_server_tool_decorator

    # `@(x)()` is invalid; use a Subscript decorator instead.
    src = "@regs[0]\ndef f():\n    pass\n"
    tree = ast.parse(src)
    dec = tree.body[0].decorator_list[0]  # ty: ignore[unresolved-attribute]  # why: stub object exposes attributes only at runtime; static checker can't see them
    assert is_a2kit_tool_decorator(dec) is False
    assert is_server_tool_decorator(dec) is False


def test_iter_string_literals_skips_non_string_elts() -> None:
    """Tuple containing a non-string literal is skipped silently."""
    import ast

    from a2kit.packages.lint.rules.detect import iter_string_literals

    tree = ast.parse("x = ('a', 1, None, 'b')")
    rhs = tree.body[0].value  # ty: ignore[unresolved-attribute]  # why: stub object exposes attributes only at runtime; static checker can't see them
    out = [c.value for c in iter_string_literals(rhs)]
    assert out == ["a", "b"]


def test_iter_string_literals_returns_nothing_for_non_container() -> None:
    """Non-container expression yields nothing."""
    import ast

    from a2kit.packages.lint.rules.detect import iter_string_literals

    tree = ast.parse("x = 'just a string'")
    rhs = tree.body[0].value  # ty: ignore[unresolved-attribute]  # why: stub object exposes attributes only at runtime; static checker can't see them
    assert list(iter_string_literals(rhs)) == []
