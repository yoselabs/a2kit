"""Tests for cross-cutting helpers in `a2kit.packages.lint.rules.__init__`.

Lives at the package-test directory (not per-rule) since these helpers
aren't owned by a single rule module.
"""

from __future__ import annotations

from pathlib import Path

from a2kit.packages.lint.rules.cross import (
    rule_a2k006_cross,
)


def _write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _codes(findings: object) -> set[str]:
    return {f.rule for f in findings}  # type: ignore[union-attr]


# --------------------------- rules/__init__.py decorator helpers --------------------------- #


def test_decorator_helpers_recognize_bare_tool_name() -> None:
    """`@tool` (Name form) is recognized — covers `is_a2kit_tool_decorator` Name branch."""
    import ast

    from a2kit.packages.lint.rules import is_a2kit_tool_decorator, is_server_tool_decorator, is_tool_function

    src = "@tool\ndef f():\n    pass\n"
    tree = ast.parse(src)
    fn = tree.body[0]
    dec = fn.decorator_list[0]
    assert is_a2kit_tool_decorator(dec) is True
    # `@tool` is a Name (not Attribute) — server detector returns False.
    assert is_server_tool_decorator(dec) is False
    assert is_tool_function(fn) is True


def test_decorator_helpers_recognize_server_tool_attr() -> None:
    """`@server.tool()` (Attribute form, non-a2kit) — only server detector returns True."""
    import ast

    from a2kit.packages.lint.rules import is_a2kit_tool_decorator, is_server_tool_decorator

    src = "@server.tool()\ndef f():\n    pass\n"
    tree = ast.parse(src)
    fn = tree.body[0]
    dec = fn.decorator_list[0]
    # is_a2kit_tool_decorator: target.value is a Name 'server' not in {'a2kit', 'tools'} → False
    assert is_a2kit_tool_decorator(dec) is False
    assert is_server_tool_decorator(dec) is True


def test_decorator_helpers_unknown_decorator_returns_false() -> None:
    import ast

    from a2kit.packages.lint.rules import is_a2kit_tool_decorator, is_server_tool_decorator

    src = "@somemod.somemethod\ndef f():\n    pass\n"
    tree = ast.parse(src)
    dec = tree.body[0].decorator_list[0]
    assert is_a2kit_tool_decorator(dec) is False
    # The Attribute is `somemod.somemethod` (attr != 'tool') → server detector also False
    assert is_server_tool_decorator(dec) is False


def test_decorator_helpers_constant_decorator_returns_false() -> None:
    """`@(some_factory())()` Call where target is itself a Call (not Name/Attribute) → False."""
    import ast

    from a2kit.packages.lint.rules import is_a2kit_tool_decorator, is_server_tool_decorator

    # `@(x)()` is invalid; use a Subscript decorator instead.
    src = "@regs[0]\ndef f():\n    pass\n"
    tree = ast.parse(src)
    dec = tree.body[0].decorator_list[0]
    assert is_a2kit_tool_decorator(dec) is False
    assert is_server_tool_decorator(dec) is False


def test_iter_string_literals_skips_non_string_elts() -> None:
    """Tuple containing a non-string literal is skipped silently."""
    import ast

    from a2kit.packages.lint.rules import iter_string_literals

    tree = ast.parse("x = ('a', 1, None, 'b')")
    rhs = tree.body[0].value
    out = [c.value for c in iter_string_literals(rhs)]
    assert out == ["a", "b"]


def test_iter_string_literals_returns_nothing_for_non_container() -> None:
    """Non-container expression yields nothing."""
    import ast

    from a2kit.packages.lint.rules import iter_string_literals

    tree = ast.parse("x = 'just a string'")
    rhs = tree.body[0].value
    assert list(iter_string_literals(rhs)) == []


def test_rule_a2k006_cross_is_idempotent_for_unique_descriptions() -> None:
    per_file: dict[str, dict[str, list[str]]] = {
        "/a.py": {"foo": ["alpha description here long enough"]},
        "/b.py": {"foo": ["beta description here long enough"]},
    }
    findings = list(rule_a2k006_cross(per_file))
    assert findings == []
