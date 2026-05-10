"""Coverage uplift for `lint.rules.{caps, cross, importing, conn, budget}`.

Aims at the long-uncovered branches: re-export resolution for capability
constants (caps.py), router/tool/capability collision detection (cross.py),
fastmcp-import allowlist edge cases (importing.py), and tuple/dict placeholder
shapes for conn.py.
"""

from __future__ import annotations

from pathlib import Path

from a2kit.packages.lint.rules.caps import _reset_reexport_cache
from a2kit.packages.lint.rules.cross import (
    collect_param_descriptions,
    collect_router_names,
    collect_tool_names,
    rule_a2k006_cross,
    rule_a2k008_cross,
)
from a2kit.packages.lint.static import (
    A2K006,
    A2K008,
    A2K009,
    A2K012,
    A2K014,
    A2K_CONN_LIST_PLACEHOLDER,
    A2K_IMPORT_DISCIPLINE,
    run_static_rules,
)


def _write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _codes(findings: object) -> set[str]:
    return {f.rule for f in findings}  # type: ignore[union-attr]


# --------------------------- caps.py: re-export resolution --------------------------- #


def test_a2k012_silent_for_local_final_str_constant(tmp_path: Path) -> None:
    """Custom capability passed as `Final[str]` Name → silent."""
    _write(tmp_path / "src" / "pyproject.toml", "")
    body = (
        "from typing import Final\n"
        "import a2kit\n"
        "MY_CAP: Final[str] = 'my-cap'\n"
        "@a2kit.tool(capabilities={MY_CAP})\n"
        "def t() -> int:\n"
        "    return 1\n"
    )
    p = _write(tmp_path / "src" / "m.py", body)
    findings = run_static_rules([p])
    assert A2K012 not in _codes(findings)


def test_a2k012_silent_for_imported_final_str(tmp_path: Path) -> None:
    """Constant imported from a sibling module that declares it as Final[str]."""
    _reset_reexport_cache()
    _write(tmp_path / "src" / "pyproject.toml", "")
    _write(
        tmp_path / "src" / "caps_lib.py",
        "from typing import Final\nMY_CAP: Final[str] = 'my-cap'\n",
    )
    body = "import a2kit\nfrom caps_lib import MY_CAP\n@a2kit.tool(capabilities={MY_CAP})\ndef t() -> int:\n    return 1\n"
    p = _write(tmp_path / "src" / "m.py", body)
    findings = run_static_rules([p])
    assert A2K012 not in _codes(findings)


def test_a2k012_resolves_through_reexport_chain(tmp_path: Path) -> None:
    """A → B re-export → C declares Final[str]. Cache also gets exercised on second call."""
    _reset_reexport_cache()
    _write(tmp_path / "src" / "pyproject.toml", "")
    # Package layout:
    #   src/pkg/__init__.py re-exports MY_CAP from pkg.middle
    #   src/pkg/middle.py re-exports MY_CAP from pkg.leaf
    #   src/pkg/leaf.py declares Final[str]
    _write(tmp_path / "src" / "pkg" / "__init__.py", "from pkg.middle import MY_CAP\n")
    _write(tmp_path / "src" / "pkg" / "middle.py", "from pkg.leaf import MY_CAP\n")
    _write(
        tmp_path / "src" / "pkg" / "leaf.py",
        "from typing import Final\nMY_CAP: Final[str] = 'deep'\n",
    )
    body = "import a2kit\nfrom pkg import MY_CAP\n@a2kit.tool(capabilities={MY_CAP})\ndef t() -> int:\n    return 1\n"
    p = _write(tmp_path / "src" / "m.py", body)
    findings1 = run_static_rules([p])
    findings2 = run_static_rules([p])  # second hit uses cache
    assert A2K012 not in _codes(findings1)
    assert A2K012 not in _codes(findings2)


def test_a2k012_unresolved_reexport_falls_back_to_constant_str(tmp_path: Path) -> None:
    """Cap is given as a raw string literal (not a Name) and there's no constant — A2K012 fires."""
    _reset_reexport_cache()
    _write(tmp_path / "src" / "pyproject.toml", "")
    body = "import a2kit\n@a2kit.tool(capabilities={'unknown-cap'})\ndef t() -> int:\n    return 1\n"
    p = _write(tmp_path / "src" / "m.py", body)
    findings = run_static_rules([p])
    assert A2K012 in _codes(findings)


def test_a2k009_in_list_and_tuple_containers(tmp_path: Path) -> None:
    """`capabilities=['read']` and `capabilities=('read',)` both flag."""
    _write(tmp_path / "src" / "pyproject.toml", "")
    body_list = "import a2kit\n@a2kit.tool(capabilities=['read'])\ndef t() -> int:\n    return 1\n"
    body_tuple = "import a2kit\n@a2kit.tool(capabilities=('read',))\ndef u() -> int:\n    return 1\n"
    p1 = _write(tmp_path / "src" / "m1.py", body_list)
    p2 = _write(tmp_path / "src" / "m2.py", body_tuple)
    findings1 = run_static_rules([p1])
    findings2 = run_static_rules([p2])
    assert A2K009 in _codes(findings1)
    assert A2K009 in _codes(findings2)


def test_a2k009_skipped_on_fixture_path(tmp_path: Path) -> None:
    body = "import a2kit\n@a2kit.tool(capabilities={'read'})\ndef t() -> int:\n    return 1\n"
    p = _write(tmp_path / "tests" / "fixtures" / "m.py", body)
    findings = run_static_rules([p])
    assert A2K009 not in _codes(findings)


def test_a2k009_noqa(tmp_path: Path) -> None:
    body = "import a2kit\n@a2kit.tool(capabilities={'read'})  # noqa: A2K009\ndef t() -> int:\n    return 1\n"
    p = _write(tmp_path / "src" / "m.py", body)
    findings = run_static_rules([p])
    assert A2K009 not in _codes(findings)


def test_a2k012_skipped_on_fixture_path(tmp_path: Path) -> None:
    body = "import a2kit\n@a2kit.tool(capabilities={'unknown'})\ndef t() -> int:\n    return 1\n"
    p = _write(tmp_path / "tests" / "fixtures" / "m.py", body)
    findings = run_static_rules([p])
    assert A2K012 not in _codes(findings)


def test_a2k012_noqa(tmp_path: Path) -> None:
    body = "import a2kit\n@a2kit.tool(capabilities={\n    'unknown',  # noqa: A2K012\n})\ndef t() -> int:\n    return 1\n"
    p = _write(tmp_path / "src" / "m.py", body)
    findings = run_static_rules([p])
    assert A2K012 not in _codes(findings)


def test_collect_local_final_str_names_handles_pathological_shapes() -> None:
    """Direct test of `_collect_local_final_str_names` over weird AST shapes."""
    import ast

    from a2kit.packages.lint.rules.caps import _collect_local_final_str_names

    # Non-module input (line 144) → empty set.
    expr_tree = ast.parse("1 + 1", mode="eval")
    assert _collect_local_final_str_names(expr_tree) == set()

    # AnnAssign without Subscript annotation (line 150).
    src = "from typing import Final\nMY: Final = 'x'\n"
    assert _collect_local_final_str_names(ast.parse(src)) == set()

    # Subscript base != Final (line 154).
    src2 = "from typing import List\nMY: List[str] = ['x']\n"
    assert _collect_local_final_str_names(ast.parse(src2)) == set()

    # slice is not a Name (e.g. Subscript) (line 156).
    src3 = "from typing import Final\nMY: Final[list[str]] = ['x']\n"
    assert _collect_local_final_str_names(ast.parse(src3)) == set()

    # Plain assignments (not AnnAssign) — also skipped.
    src4 = "MY = 'x'\n"
    assert _collect_local_final_str_names(ast.parse(src4)) == set()

    # AnnAssign target not a Name (e.g. Tuple/Subscript) — skipped.
    src5 = "from typing import Final\nx: Final[str]\n"  # no value, but still caught
    assert _collect_local_final_str_names(ast.parse(src5)) == {"x"}


def test_module_to_path_returns_none_for_unknown_module(tmp_path: Path) -> None:
    """Direct test of `_module_to_path` with a non-existent module."""
    from a2kit.packages.lint.rules.caps import _module_to_path

    assert _module_to_path("not_a_real_module", tmp_path) is None


def test_has_final_str_assign_handles_non_module() -> None:
    import ast

    from a2kit.packages.lint.rules.caps import _has_final_str_assign

    expr_tree = ast.parse("1 + 1", mode="eval")
    assert _has_final_str_assign(expr_tree, "X") is False


def test_find_reexport_handles_non_module() -> None:
    import ast

    from a2kit.packages.lint.rules.caps import _find_reexport

    expr_tree = ast.parse("1 + 1", mode="eval")
    assert _find_reexport(expr_tree, "X") is None


def test_a2k012_silent_for_builtin_string_in_set(tmp_path: Path) -> None:
    """Built-in caps in `capabilities` set raise A2K009 not A2K012 — A2K012 short-circuits."""
    body = "import a2kit\n@a2kit.tool(capabilities={'read'})\ndef t() -> int:\n    return 1\n"
    p = _write(tmp_path / "src" / "m.py", body)
    findings = run_static_rules([p])
    # A2K009 fires; A2K012 does NOT fire on built-ins.
    assert A2K009 in _codes(findings)
    assert A2K012 not in _codes(findings)


# --------------------------- cross.py: A2K006 / A2K008 --------------------------- #


def test_a2k006_cross_fires_for_thrice_repeated_param_doc(tmp_path: Path) -> None:
    """Same `param: long-description` repeated across 3 different files → A2K006."""
    body_template = 'import a2kit\n@a2kit.tool()\ndef t{n}() -> int:\n    """Yo.\n\n    foo: this is a description longer than twenty chars\n    """\n    return 1\n'
    paths = [_write(tmp_path / "src" / f"m{i}.py", body_template.format(n=i)) for i in range(3)]
    findings = run_static_rules(paths)
    assert A2K006 in _codes(findings)


def test_a2k006_cross_silent_under_threshold(tmp_path: Path) -> None:
    body_template = (
        'import a2kit\n@a2kit.tool()\ndef t{n}() -> int:\n    """foo: a long enough description here yes really"""\n    return 1\n'
    )
    paths = [_write(tmp_path / "src" / f"m{i}.py", body_template.format(n=i)) for i in range(2)]
    findings = run_static_rules(paths)
    assert A2K006 not in _codes(findings)


def test_collect_param_descriptions_filters_short_and_non_ident() -> None:
    """`<20-char` text or non-identifier name is filtered out."""
    import ast

    src = (
        "import a2kit\n"
        "@a2kit.tool()\n"
        "def t() -> int:\n"
        '    """\n'
        "    foo: short\n"
        "    not-an-ident: this description is over twenty characters fine\n"
        "    bar: this description is also over twenty characters yes really\n"
        "    no_colon_line\n"
        '    """\n'
        "    return 1\n"
    )
    tree = ast.parse(src)
    out = collect_param_descriptions(tree)
    assert "bar" in out
    assert "foo" not in out
    assert "not-an-ident" not in out


def test_collect_router_names_from_class_name_attribute() -> None:
    import ast

    src = "import a2kit\nclass R(a2kit.Router):\n    name = 'my_router'\n"
    tree = ast.parse(src)
    assert "my_router" in collect_router_names(tree)


def test_collect_router_names_from_call_keyword() -> None:
    import ast

    src = "import a2kit\nfoo(name='dynamic_router')\n"
    tree = ast.parse(src)
    assert "dynamic_router" in collect_router_names(tree)


def test_collect_tool_names_uses_explicit_tool_name() -> None:
    import ast

    src = "import a2kit\n@a2kit.tool(tool_name='aliased')\ndef t() -> int:\n    return 1\n"
    tree = ast.parse(src)
    names = collect_tool_names(tree)
    # both the explicit tool_name AND the function def name end up in collected set.
    assert "aliased" in names
    assert "t" in names


def test_a2k008_cross_router_tool_collision() -> None:
    """Same name used as router AND tool → collision."""
    per_file = {
        "/x/router.py": ({"shared"}, set()),
        "/x/tool.py": (set(), {"shared"}),
    }
    findings = list(rule_a2k008_cross(per_file))
    assert any(f.rule == A2K008 for f in findings)


def test_a2k008_cross_router_capability_collision() -> None:
    """Router named after a built-in cap → collision."""
    per_file = {"/x/r.py": ({"read"}, set())}
    findings = list(rule_a2k008_cross(per_file))
    assert any(f.rule == A2K008 for f in findings)


def test_a2k008_cross_tool_capability_collision() -> None:
    per_file = {"/x/t.py": (set(), {"write"})}
    findings = list(rule_a2k008_cross(per_file))
    assert any(f.rule == A2K008 for f in findings)


def test_a2k008_cross_no_collision_silent() -> None:
    per_file = {
        "/x/r.py": ({"router_a"}, set()),
        "/x/t.py": (set(), {"tool_a"}),
    }
    findings = list(rule_a2k008_cross(per_file))
    assert findings == []


def test_a2k006_cross_disabled_skips() -> None:
    """`disabled=[A2K006]` — collector is not called, no findings."""
    body = 'import a2kit\n@a2kit.tool()\ndef t() -> int:\n    """foo: a long enough description here yes really"""\n    return 1\n'
    p = _write(Path("/tmp/_disabled_a2k006.py"), body)
    try:
        findings = run_static_rules([p], disabled=[A2K006])
        assert A2K006 not in _codes(findings)
    finally:
        p.unlink(missing_ok=True)


# --------------------------- importing.py: allowlist edges --------------------------- #


def test_import_discipline_plain_import_form_fires(tmp_path: Path) -> None:
    """`import fastmcp` (Import, not ImportFrom) outside allowlist."""
    body = "import fastmcp\n"
    p = _write(tmp_path / "src" / "a2kit" / "user_app.py", body)
    findings = run_static_rules([p])
    assert A2K_IMPORT_DISCIPLINE in _codes(findings)


def test_import_discipline_dotted_module_fires(tmp_path: Path) -> None:
    """`import fastmcp.server` is also covered."""
    body = "import fastmcp.server\n"
    p = _write(tmp_path / "src" / "a2kit" / "user_app.py", body)
    findings = run_static_rules([p])
    assert A2K_IMPORT_DISCIPLINE in _codes(findings)


def test_import_discipline_other_imports_silent(tmp_path: Path) -> None:
    body = "import os\nfrom typing import Any\n"
    p = _write(tmp_path / "src" / "a2kit" / "user_app.py", body)
    findings = run_static_rules([p])
    assert A2K_IMPORT_DISCIPLINE not in _codes(findings)


def test_import_discipline_skipped_on_fixture_path(tmp_path: Path) -> None:
    body = "from fastmcp import FastMCP\n"
    p = _write(tmp_path / "tests" / "fixtures" / "m.py", body)
    findings = run_static_rules([p])
    assert A2K_IMPORT_DISCIPLINE not in _codes(findings)


def test_import_discipline_silent_inside_otel_dir(tmp_path: Path) -> None:
    body = "from fastmcp import FastMCP\n"
    p = _write(tmp_path / "src" / "a2kit" / "packages" / "otel" / "middleware.py", body)
    findings = run_static_rules([p])
    assert A2K_IMPORT_DISCIPLINE not in _codes(findings)


def test_import_discipline_silent_inside_cli_context(tmp_path: Path) -> None:
    """``packages/cli/context.py`` is allowlisted for the lazy elicit() import."""
    body = "from fastmcp.server.elicitation import AcceptedElicitation\n"
    p = _write(tmp_path / "src" / "a2kit" / "packages" / "cli" / "context.py", body)
    findings = run_static_rules([p])
    assert A2K_IMPORT_DISCIPLINE not in _codes(findings)


def test_user_tool_with_fastmcp_context_annotation_is_silent(tmp_path: Path) -> None:
    """Tool annotations ``ctx: fastmcp.Context`` import fastmcp at module top.

    User code under their own package isn't subject to A2K-IMPORT-DISCIPLINE
    (the rule only fires inside ``a2kit/``). This regression locks that in
    so portable tool authors aren't penalized for using the real type.
    """
    body = "from fastmcp import Context\nasync def my_tool(*, ctx: Context) -> dict:\n    return {}\n"
    p = _write(tmp_path / "user_app" / "tools.py", body)
    findings = run_static_rules([p])
    assert A2K_IMPORT_DISCIPLINE not in _codes(findings)


def test_import_discipline_noqa(tmp_path: Path) -> None:
    body = "from fastmcp import FastMCP  # noqa: A2K-IMPORT-DISCIPLINE\n"
    p = _write(tmp_path / "src" / "a2kit" / "user_app.py", body)
    findings = run_static_rules([p])
    assert A2K_IMPORT_DISCIPLINE not in _codes(findings)


# --------------------------- conn.py: tuple/dict shapes --------------------------- #


def test_conn_list_placeholder_in_tuple(tmp_path: Path) -> None:
    body = "from a2kit.connections import ConnectionConfig\nclass C(ConnectionConfig):\n    tags: tuple = ('${MY_TAG}', 'plain')\n"
    p = _write(tmp_path / "src" / "m.py", body)
    findings = run_static_rules([p])
    assert A2K_CONN_LIST_PLACEHOLDER in _codes(findings)


def test_conn_list_placeholder_in_set(tmp_path: Path) -> None:
    body = "from a2kit.connections import ConnectionConfig\nclass C(ConnectionConfig):\n    tags: set = {'${MY_TAG}', 'plain'}\n"
    p = _write(tmp_path / "src" / "m.py", body)
    findings = run_static_rules([p])
    assert A2K_CONN_LIST_PLACEHOLDER in _codes(findings)


def test_conn_list_placeholder_nested_dict_value(tmp_path: Path) -> None:
    """Recursion into nested list inside dict value."""
    body = "from a2kit.connections import ConnectionConfig\nclass C(ConnectionConfig):\n    headers: dict = {'auth': ['${TOKEN}']}\n"
    p = _write(tmp_path / "src" / "m.py", body)
    findings = run_static_rules([p])
    assert A2K_CONN_LIST_PLACEHOLDER in _codes(findings)


def test_conn_list_placeholder_dict_key_with_placeholder(tmp_path: Path) -> None:
    """Dict KEY containing ${VAR} also flags (covers the keys-walk branch)."""
    body = "from a2kit.connections import ConnectionConfig\nclass C(ConnectionConfig):\n    map: dict = {'${TOKEN}': 'v'}\n"
    p = _write(tmp_path / "src" / "m.py", body)
    findings = run_static_rules([p])
    assert A2K_CONN_LIST_PLACEHOLDER in _codes(findings)


def test_conn_list_placeholder_skipped_on_fixture_path(tmp_path: Path) -> None:
    body = "from a2kit.connections import ConnectionConfig\nclass C(ConnectionConfig):\n    tags: list = ['${MY_TAG}']\n"
    p = _write(tmp_path / "tests" / "fixtures" / "m.py", body)
    findings = run_static_rules([p])
    assert A2K_CONN_LIST_PLACEHOLDER not in _codes(findings)


def test_conn_list_placeholder_no_value_silent(tmp_path: Path) -> None:
    """Type-only `AnnAssign` with no value (e.g. abstract field) — silent."""
    body = "from a2kit.connections import ConnectionConfig\nclass C(ConnectionConfig):\n    tags: list\n"
    p = _write(tmp_path / "src" / "m.py", body)
    findings = run_static_rules([p])
    assert A2K_CONN_LIST_PLACEHOLDER not in _codes(findings)


def test_conn_list_placeholder_non_collection_value_silent(tmp_path: Path) -> None:
    """`AnnAssign` value is a function call — not list/tuple/set/dict, silent."""
    body = (
        "from a2kit.connections import ConnectionConfig\ndef factory(): return []\nclass C(ConnectionConfig):\n    tags: list = factory()\n"
    )
    p = _write(tmp_path / "src" / "m.py", body)
    findings = run_static_rules([p])
    assert A2K_CONN_LIST_PLACEHOLDER not in _codes(findings)


def test_conn_list_placeholder_noqa(tmp_path: Path) -> None:
    body = (
        "from a2kit.connections import ConnectionConfig\n"
        "class C(ConnectionConfig):\n"
        "    tags: list = ['${MY_TAG}']  # noqa: A2K-CONN-LIST-PLACEHOLDER\n"
    )
    p = _write(tmp_path / "src" / "m.py", body)
    findings = run_static_rules([p])
    assert A2K_CONN_LIST_PLACEHOLDER not in _codes(findings)


# --------------------------- budget.py edges --------------------------- #


def test_a2k014_just_under_threshold_silent(tmp_path: Path) -> None:
    body = "x = 1\n" * 100
    p = _write(tmp_path / "src" / "m.py", body)
    findings = run_static_rules([p])
    assert A2K014 not in _codes(findings)


# --------------------------- A2K006 cross is wired through `run_static_rules` --------------------------- #


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
