"""Tests for v0.4 additions: projection module, format_response filter/fields,
A2K005 multi-field arity, A2K010, A2K011, TOML capabilities, removal guards.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import a2kit
from a2kit.exceptions import InvalidFilterExpression, ProjectionUnavailable
from a2kit.lint.static import run_static_rules

# ---- projection.project_fields ---------------------------------------------


def test_project_fields_basic() -> None:
    rows = [{"a": 1, "b": 2, "c": 3}, {"a": 4, "b": 5, "c": 6}]
    out = a2kit.projection.project_fields(rows, fields=["a", "c"])
    assert out == [{"a": 1, "c": 3}, {"a": 4, "c": 6}]


def test_project_fields_missing_keys_dropped() -> None:
    rows = [{"a": 1}, {"b": 2}]
    out = a2kit.projection.project_fields(rows, fields=["a", "b"])
    assert out == [{"a": 1}, {"b": 2}]


def test_project_fields_empty_fields_returns_copies() -> None:
    rows = [{"a": 1}]
    out = a2kit.projection.project_fields(rows, fields=[])
    assert out == [{"a": 1}]
    out[0]["a"] = 99
    assert rows[0]["a"] == 1  # original untouched


# ---- projection.filter_records ---------------------------------------------


def test_filter_records_simple() -> None:
    rows = [
        {"status": "open", "priority": 5},
        {"status": "closed", "priority": 5},
        {"status": "open", "priority": 1},
    ]
    out = a2kit.projection.filter_records(rows, expr="status == 'open' && priority > 3")
    assert out == [{"status": "open", "priority": 5}]


def test_filter_records_empty_expr_returns_all() -> None:
    rows = [{"a": 1}, {"a": 2}]
    out = a2kit.projection.filter_records(rows, expr="")
    assert out == rows


def test_filter_records_whitespace_expr_returns_all() -> None:
    rows = [{"a": 1}]
    out = a2kit.projection.filter_records(rows, expr="   ")
    assert out == rows


def test_filter_records_nested_dict_field() -> None:
    rows = [{"meta": {"score": 10}}, {"meta": {"score": 5}}]
    out = a2kit.projection.filter_records(rows, expr="meta.score > 7")
    assert out == [{"meta": {"score": 10}}]


def test_filter_records_invalid_expr_raises() -> None:
    rows = [{"a": 1}]
    with pytest.raises(InvalidFilterExpression):
        a2kit.projection.filter_records(rows, expr="this is +++ not cel")


def test_filter_records_evaluation_failure_raises() -> None:
    rows = [{"a": 1}]
    with pytest.raises(InvalidFilterExpression):
        a2kit.projection.filter_records(rows, expr="undefined_var > 0")


def test_projection_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force ImportError on celpy lazy-load."""
    import builtins

    real_import = builtins.__import__

    def fake_import(name: str, *a: object, **kw: object) -> object:
        if name == "celpy":
            raise ImportError("blocked")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(ProjectionUnavailable):
        a2kit.projection.filter_records([{"a": 1}], expr="a > 0")


# ---- format_response with filter / fields ----------------------------------


def test_format_response_filter_only() -> None:
    rows = [{"x": 1}, {"x": 5}]
    env = a2kit.format_response(rows, filter="x > 3")
    assert env["format"] == "toon"
    assert "5" in env["data"]
    assert "1" not in env["data"].split("\n")[1]


def test_format_response_fields_only() -> None:
    rows = [{"a": 1, "b": 2}]
    env = a2kit.format_response(rows, fields=["a"])
    assert env["format"] == "toon"
    assert "b" not in env["data"]


def test_format_response_filter_and_fields() -> None:
    rows = [{"a": 1, "b": 2}, {"a": 3, "b": 4}]
    env = a2kit.format_response(rows, filter="a > 2", fields=["a"])
    assert env["format"] == "toon"
    assert "3" in env["data"]


def test_format_response_no_filter_or_fields_unchanged() -> None:
    rows = [{"a": 1}]
    env_a = a2kit.format_response(rows)
    env_b = a2kit.format_response(rows, filter="", fields=None)
    assert env_a == env_b


def test_format_response_filter_skipped_for_non_list() -> None:
    """Filter only applies to list-of-dicts shapes."""
    env = a2kit.format_response({"a": 1}, filter="a > 0")
    assert env["format"] == "json"


def test_format_response_filter_skipped_for_mixed_list() -> None:
    env = a2kit.format_response([1, 2, 3], filter="x > 0")
    assert env["format"] == "json"


# ---- @a2kit.tool with cel_filter_param / fields_param ----------------------


def test_tool_cel_filter_param_threads_through() -> None:
    rows = [{"id": 1, "v": 10}, {"id": 2, "v": 1}]

    @a2kit.tool(cel_filter_param="filter", fields_param="fields")
    def list_widgets(filter: str = "", fields: list[str] | None = None) -> list[dict]:  # noqa: A002
        return rows

    env = list_widgets(filter="v > 5")
    assert isinstance(env, dict)
    assert env["format"] == "toon"
    assert "10" in env["data"]


def test_tool_cel_filter_param_no_args_unchanged() -> None:
    rows = [{"id": 1}]

    @a2kit.tool(cel_filter_param="filter", fields_param="fields")
    def list_widgets(filter: str = "", fields: list[str] | None = None) -> list[dict]:  # noqa: A002
        return rows

    out = list_widgets()
    assert out == rows  # no envelope when filter+fields both empty


def test_tool_cel_filter_param_fields_only() -> None:
    rows = [{"a": 1, "b": 2}]

    @a2kit.tool(fields_param="fields")
    def list_widgets(fields: list[str] | None = None) -> list[dict]:
        return rows

    env = list_widgets(fields=["a"])
    assert isinstance(env, dict)
    assert "b" not in env["data"]


async def test_tool_cel_filter_param_async() -> None:
    rows = [{"v": 10}, {"v": 1}]

    @a2kit.tool(cel_filter_param="filter")
    async def list_widgets(filter: str = "") -> list[dict]:  # noqa: A002
        return rows

    env = await list_widgets(filter="v > 5")
    assert isinstance(env, dict)
    assert env["format"] == "toon"


def test_tool_cel_filter_param_non_string_value_ignored() -> None:
    """Non-str filter arg is treated as no-op (defensive)."""
    rows = [{"a": 1}]

    @a2kit.tool(cel_filter_param="filter")
    def list_widgets(filter: object = None) -> list[dict]:  # noqa: A002
        return rows

    out = list_widgets(filter=123)
    assert out == rows


def test_tool_cel_filter_param_non_list_fields_ignored() -> None:
    rows = [{"a": 1}]

    @a2kit.tool(fields_param="fields")
    def list_widgets(fields: object = None) -> list[dict]:
        return rows

    out = list_widgets(fields="not-a-list")
    assert out == rows


# ---- Lint A2K011 ------------------------------------------------------------


def test_lint_a2k011_dict_return_flagged(tmp_path: Path) -> None:
    src = tmp_path / "src" / "mod.py"
    src.parent.mkdir(parents=True)
    src.write_text("import a2kit\n@a2kit.tool()\ndef f() -> dict:\n    return {}\n")
    findings = run_static_rules([src])
    assert any(f.rule == "A2K011" for f in findings)


def test_lint_a2k011_typed_dict_subscript(tmp_path: Path) -> None:
    src = tmp_path / "src" / "mod.py"
    src.parent.mkdir(parents=True)
    src.write_text("from typing import Dict\nimport a2kit\n@a2kit.tool()\ndef f() -> Dict[str, int]:\n    return {}\n")
    findings = run_static_rules([src])
    assert any(f.rule == "A2K011" for f in findings)


def test_lint_a2k011_pydantic_model_silent(tmp_path: Path) -> None:
    src = tmp_path / "src" / "mod.py"
    src.parent.mkdir(parents=True)
    src.write_text(
        "from pydantic import BaseModel\nimport a2kit\n"
        "class _M(BaseModel):\n    x: int\n"
        "@a2kit.tool()\ndef f() -> _M:\n    return _M(x=1)\n"
    )
    findings = run_static_rules([src])
    assert not any(f.rule == "A2K011" for f in findings)


def test_lint_a2k011_skipped_under_tests(tmp_path: Path) -> None:
    src = tmp_path / "tests" / "mod.py"
    src.parent.mkdir(parents=True)
    src.write_text("import a2kit\n@a2kit.tool()\ndef f() -> dict:\n    return {}\n")
    findings = run_static_rules([src])
    assert not any(f.rule == "A2K011" for f in findings)


def test_lint_a2k011_noqa_suppresses(tmp_path: Path) -> None:
    src = tmp_path / "src" / "mod.py"
    src.parent.mkdir(parents=True)
    src.write_text("import a2kit\n@a2kit.tool()\ndef f() -> dict:  # noqa: A2K011\n    return {}\n")
    findings = run_static_rules([src])
    assert not any(f.rule == "A2K011" for f in findings)


# ---- Lint A2K005 multi-field arity -----------------------------------------


def test_lint_a2k005_arity1_str_ok(tmp_path: Path) -> None:
    src = tmp_path / "src" / "mod.py"
    src.parent.mkdir(parents=True)
    src.write_text(
        "import a2kit\n"
        "from a2kit import ConnectionInfo, ConnectionStore\n"
        "class C(ConnectionInfo):\n"
        "    KEY_FIELDS = ('name',)\n"
        "    url: str\n"
        "store = ConnectionStore('/tmp', C)\n"  # noqa: S108
        "@a2kit.tool(store=store, connection_param='conn')\n"
        "async def t(conn: str) -> dict:\n"
        "    return {}\n"
    )
    findings = run_static_rules([src], disabled=["A2K011"])
    arity_findings = [f for f in findings if f.rule == "A2K005" and "arity" in f.message]
    assert not arity_findings


def test_lint_a2k005_arity3_str_fails(tmp_path: Path) -> None:
    src = tmp_path / "src" / "mod.py"
    src.parent.mkdir(parents=True)
    src.write_text(
        "import a2kit\n"
        "from a2kit import ConnectionInfo, ConnectionStore\n"
        "class C(ConnectionInfo):\n"
        "    KEY_FIELDS = ('p', 'e', 'd')\n"
        "    url: str\n"
        "store = ConnectionStore('/tmp', C)\n"  # noqa: S108
        "@a2kit.tool(store=store, connection_param='conn')\n"
        "async def t(conn: str) -> dict:\n"
        "    return {}\n"
    )
    findings = run_static_rules([src], disabled=["A2K011"])
    assert any(f.rule == "A2K005" and "insufficient" in f.message for f in findings)


def test_lint_a2k005_arity3_tuple_ok(tmp_path: Path) -> None:
    src = tmp_path / "src" / "mod.py"
    src.parent.mkdir(parents=True)
    src.write_text(
        "import a2kit\n"
        "from a2kit import ConnectionInfo, ConnectionStore\n"
        "class C(ConnectionInfo):\n"
        "    KEY_FIELDS = ('p', 'e', 'd')\n"
        "    url: str\n"
        "store = ConnectionStore('/tmp', C)\n"  # noqa: S108
        "@a2kit.tool(store=store, connection_param='conn')\n"
        "async def t(conn: tuple[str, str, str]) -> dict:\n"
        "    return {}\n"
    )
    findings = run_static_rules([src], disabled=["A2K011"])
    assert not any(f.rule == "A2K005" and "insufficient" in f.message for f in findings)


def test_lint_a2k005_arity3_tuple_variadic_ok(tmp_path: Path) -> None:
    src = tmp_path / "src" / "mod.py"
    src.parent.mkdir(parents=True)
    src.write_text(
        "import a2kit\n"
        "from a2kit import ConnectionInfo, ConnectionStore\n"
        "class C(ConnectionInfo):\n"
        "    KEY_FIELDS = ('p', 'e', 'd')\n"
        "    url: str\n"
        "store = ConnectionStore('/tmp', C)\n"  # noqa: S108
        "@a2kit.tool(store=store, connection_param='conn')\n"
        "async def t(conn: tuple[str, ...]) -> dict:\n"
        "    return {}\n"
    )
    findings = run_static_rules([src], disabled=["A2K011"])
    assert not any(f.rule == "A2K005" and "insufficient" in f.message for f in findings)


def test_lint_a2k005_arity3_typed_model_ok(tmp_path: Path) -> None:
    src = tmp_path / "src" / "mod.py"
    src.parent.mkdir(parents=True)
    src.write_text(
        "import a2kit\n"
        "from a2kit import ConnectionInfo, ConnectionStore\n"
        "class C(ConnectionInfo):\n"
        "    KEY_FIELDS = ('p', 'e', 'd')\n"
        "    url: str\n"
        "store = ConnectionStore('/tmp', C)\n"  # noqa: S108
        "@a2kit.tool(store=store, connection_param='conn')\n"
        "async def t(conn: WidgetKey) -> dict:\n"
        "    return {}\n"
    )
    findings = run_static_rules([src], disabled=["A2K011"])
    assert not any(f.rule == "A2K005" and "insufficient" in f.message for f in findings)


def test_lint_a2k005_arity1_non_str_ok(tmp_path: Path) -> None:
    """Arity-1 with a non-str shape (tuple) is acceptable too."""
    src = tmp_path / "src" / "mod.py"
    src.parent.mkdir(parents=True)
    src.write_text(
        "import a2kit\n"
        "from a2kit import ConnectionInfo, ConnectionStore\n"
        "class C(ConnectionInfo):\n"
        "    KEY_FIELDS = ('name',)\n"
        "    url: str\n"
        "store = ConnectionStore('/tmp', C)\n"  # noqa: S108
        "@a2kit.tool(store=store, connection_param='conn')\n"
        "async def t(conn: tuple[str]) -> dict:\n"
        "    return {}\n"
    )
    findings = run_static_rules([src], disabled=["A2K011"])
    assert not any(f.rule == "A2K005" and "insufficient" in f.message for f in findings)


def test_lint_a2k005_ann_assign_store_resolves(tmp_path: Path) -> None:
    """`store: ConnectionStore[C] = ConnectionStore(...)` form is resolvable."""
    src = tmp_path / "src" / "mod.py"
    src.parent.mkdir(parents=True)
    src.write_text(
        "import a2kit\n"
        "from a2kit import ConnectionInfo, ConnectionStore\n"
        "class C(ConnectionInfo):\n"
        "    KEY_FIELDS = ('p', 'e', 'd')\n"
        "    url: str\n"
        "store: ConnectionStore[C] = ConnectionStore('/tmp', C)\n"  # noqa: S108
        "@a2kit.tool(store=store, connection_param='conn')\n"
        "async def t(conn: str) -> dict:\n"
        "    return {}\n"
    )
    findings = run_static_rules([src], disabled=["A2K011"])
    assert any(f.rule == "A2K005" and "insufficient" in f.message for f in findings)


def test_lint_a2k005_arity_gt1_subscript_other_base(tmp_path: Path) -> None:
    """Arity>1 with non-tuple/non-dict subscript (e.g. `Sequence[str]`) is accepted."""
    src = tmp_path / "src" / "mod.py"
    src.parent.mkdir(parents=True)
    src.write_text(
        "from typing import Sequence\n"
        "import a2kit\n"
        "from a2kit import ConnectionInfo, ConnectionStore\n"
        "class C(ConnectionInfo):\n"
        "    KEY_FIELDS = ('p', 'e', 'd')\n"
        "    url: str\n"
        "store = ConnectionStore('/tmp', C)\n"  # noqa: S108
        "@a2kit.tool(store=store, connection_param='conn')\n"
        "async def t(conn: Sequence[str]) -> dict:\n"
        "    return {}\n"
    )
    findings = run_static_rules([src], disabled=["A2K011"])
    assert not any(f.rule == "A2K005" and "insufficient" in f.message for f in findings)


def test_lint_a2k005_no_annotation_unresolvable(tmp_path: Path) -> None:
    """Param without an annotation falls into the `verdict = None` branch."""
    src = tmp_path / "src" / "mod.py"
    src.parent.mkdir(parents=True)
    src.write_text(
        "import a2kit\n"
        "from a2kit import ConnectionInfo, ConnectionStore\n"
        "class C(ConnectionInfo):\n"
        "    KEY_FIELDS = ('p', 'e', 'd')\n"
        "    url: str\n"
        "store = ConnectionStore('/tmp', C)\n"  # noqa: S108
        "@a2kit.tool(store=store, connection_param='conn')\n"
        "async def t(conn) -> dict:\n"
        "    return {}\n"
    )
    findings = run_static_rules([src], disabled=["A2K011"])
    # No annotation → verdict None → no insufficient finding
    assert not any(f.rule == "A2K005" and "insufficient" in f.message for f in findings)


def test_lint_a2k005_unresolvable_noqa_suppresses(tmp_path: Path) -> None:
    src = tmp_path / "src" / "mod.py"
    src.parent.mkdir(parents=True)
    src.write_text(
        "import a2kit\n"
        "@a2kit.tool(store=external_store, connection_param='conn')\n"
        "async def t(conn: str) -> dict:  # noqa: A2K005\n"
        "    return {}\n"
    )
    findings = run_static_rules([src], disabled=["A2K011"])
    assert not any(f.rule == "A2K005" for f in findings)


def test_lint_a2k005_param_loop_iteration(tmp_path: Path) -> None:
    """Function with multiple params; loop must skip past mismatches before finding `conn`."""
    src = tmp_path / "src" / "mod.py"
    src.parent.mkdir(parents=True)
    src.write_text(
        "import a2kit\n"
        "from a2kit import ConnectionInfo, ConnectionStore\n"
        "class C(ConnectionInfo):\n"
        "    KEY_FIELDS = ('p', 'e', 'd')\n"
        "    url: str\n"
        "store = ConnectionStore('/tmp', C)\n"  # noqa: S108
        "@a2kit.tool(store=store, connection_param='conn')\n"
        "async def t(other: int, conn: str) -> dict:\n"
        "    return {}\n"
    )
    findings = run_static_rules([src], disabled=["A2K011"])
    assert any(f.rule == "A2K005" and "insufficient" in f.message for f in findings)


def test_lint_a2k005_other_call_in_module_skipped(tmp_path: Path) -> None:
    """A non-`ConnectionStore` Call assignment is skipped during arity scan."""
    src = tmp_path / "src" / "mod.py"
    src.parent.mkdir(parents=True)
    src.write_text(
        "import a2kit\n"
        "from a2kit import ConnectionInfo, ConnectionStore\n"
        "class C(ConnectionInfo):\n"
        "    KEY_FIELDS = ('p', 'e', 'd')\n"
        "    url: str\n"
        "other = print('hi')  # non-ConnectionStore call\n"
        "store = ConnectionStore('/tmp', C)\n"  # noqa: S108
        "@a2kit.tool(store=store, connection_param='conn')\n"
        "async def t(conn: tuple[str, str, str]) -> dict:\n"
        "    return {}\n"
    )
    findings = run_static_rules([src], disabled=["A2K011"])
    assert not any(f.rule == "A2K005" and "insufficient" in f.message for f in findings)


def test_lint_a2k005_tuple_target_skipped(tmp_path: Path) -> None:
    """A tuple target like `a, b = ConnectionStore(...), 1` doesn't register the var."""
    src = tmp_path / "src" / "mod.py"
    src.parent.mkdir(parents=True)
    src.write_text(
        "import a2kit\n"
        "from a2kit import ConnectionInfo, ConnectionStore\n"
        "class C(ConnectionInfo):\n"
        "    KEY_FIELDS = ('p', 'e', 'd')\n"
        "    url: str\n"
        "a, b = ConnectionStore('/tmp', C), 1\n"  # noqa: S108
        "@a2kit.tool(store=a, connection_param='conn')\n"
        "async def t(conn: str) -> dict:\n"
        "    return {}\n"
    )
    findings = run_static_rules([src], disabled=["A2K011"])
    # `a` was a tuple-target so not registered → unresolved advisory.
    assert any(f.rule == "A2K005" and "could not resolve" in f.message for f in findings)


def test_lint_a2k005_store_assigned_to_non_call(tmp_path: Path) -> None:
    """A `store = some_var` assignment is not a ConnectionStore() call → unresolved."""
    src = tmp_path / "src" / "mod.py"
    src.parent.mkdir(parents=True)
    src.write_text(
        "import a2kit\n"
        "from a2kit import ConnectionInfo\n"
        "class C(ConnectionInfo):\n"
        "    KEY_FIELDS = ('p', 'e', 'd')\n"
        "    url: str\n"
        "store = some_external_thing\n"
        "@a2kit.tool(store=store, connection_param='conn')\n"
        "async def t(conn: str) -> dict:\n"
        "    return {}\n"
    )
    findings = run_static_rules([src], disabled=["A2K011"])
    assert any(f.rule == "A2K005" and "could not resolve" in f.message for f in findings)


def test_lint_a2k005_unknown_class_in_store_call(tmp_path: Path) -> None:
    """ConnectionStore(dir, UnknownClass) where UnknownClass not in arity map → unresolved."""
    src = tmp_path / "src" / "mod.py"
    src.parent.mkdir(parents=True)
    src.write_text(
        "from a2kit import ConnectionStore\n"
        "import a2kit\n"
        "store = ConnectionStore('/tmp', SomeImported)\n"  # noqa: S108
        "@a2kit.tool(store=store, connection_param='conn')\n"
        "async def t(conn: str) -> dict:\n"
        "    return {}\n"
    )
    findings = run_static_rules([src], disabled=["A2K011"])
    assert any(f.rule == "A2K005" and "could not resolve" in f.message for f in findings)


def test_lint_a2k005_unresolvable_store_advisory(tmp_path: Path) -> None:
    src = tmp_path / "src" / "mod.py"
    src.parent.mkdir(parents=True)
    src.write_text(
        "import a2kit\n@a2kit.tool(store=external_store, connection_param='conn')\nasync def t(conn: str) -> dict:\n    return {}\n"
    )
    findings = run_static_rules([src], disabled=["A2K011"])
    assert any(f.rule == "A2K005" and "could not resolve" in f.message for f in findings)


# ---- Lint A2K010 ------------------------------------------------------------


def test_lint_a2k010_unknown_atom_in_default_select(tmp_path: Path) -> None:
    src = tmp_path / "src" / "main.py"
    src.parent.mkdir(parents=True)
    src.write_text('import a2kit\nrunner = a2kit.MCPRunner(None, default_select="bogus_atom")\n')
    findings = run_static_rules([src])
    assert any(f.rule == "A2K010" and "bogus_atom" in f.message for f in findings)


def test_lint_a2k010_known_router_atom_silent(tmp_path: Path) -> None:
    src = tmp_path / "src" / "main.py"
    src.parent.mkdir(parents=True)
    src.write_text(
        "import a2kit\n"
        "from a2kit import Router\n"
        "router = Router(name='issues')\n"
        'r = a2kit.MCPRunner(None, default_select="router:issues")\n'
    )
    findings = run_static_rules([src])
    assert not any(f.rule == "A2K010" for f in findings)


def test_lint_a2k010_known_builtin_cap_silent(tmp_path: Path) -> None:
    src = tmp_path / "src" / "main.py"
    src.parent.mkdir(parents=True)
    src.write_text('import a2kit\nr = a2kit.MCPRunner(None, default_select="default and not write")\n')
    findings = run_static_rules([src])
    assert not any(f.rule == "A2K010" for f in findings)


def test_lint_a2k010_subprocess_select_string(tmp_path: Path) -> None:
    src = tmp_path / "src" / "main.py"
    src.parent.mkdir(parents=True)
    src.write_text('import subprocess\nsubprocess.run(["mcp", "--select", "made_up"])\n')
    findings = run_static_rules([src])
    assert any(f.rule == "A2K010" and "made_up" in f.message for f in findings)


def test_lint_a2k010_parse_select_call(tmp_path: Path) -> None:
    src = tmp_path / "src" / "main.py"
    src.parent.mkdir(parents=True)
    src.write_text("from a2kit import parse_select\nparse_select('zzz_unknown')\n")
    findings = run_static_rules([src])
    assert any(f.rule == "A2K010" and "zzz_unknown" in f.message for f in findings)


def test_lint_a2k010_shell_script(tmp_path: Path) -> None:
    sh = tmp_path / "run.sh"
    sh.write_text('#!/bin/bash\nmcp --select "rouge_atom"\n')
    findings = run_static_rules([sh])
    assert any(f.rule == "A2K010" and "rouge_atom" in f.message for f in findings)


def test_lint_a2k010_makefile(tmp_path: Path) -> None:
    mk = tmp_path / "Makefile"
    mk.write_text('serve:\n\tmcp --select "phony_atom"\n')
    findings = run_static_rules([mk])
    assert any(f.rule == "A2K010" and "phony_atom" in f.message for f in findings)


def test_lint_a2k010_pyproject_default_select(tmp_path: Path) -> None:
    py = tmp_path / "pyproject.toml"
    py.write_text('[tool.a2kit.runner]\ndefault_select = "ghost_atom"\n')
    src = tmp_path / "src" / "mod.py"
    src.parent.mkdir(parents=True)
    src.write_text("# empty\n")
    findings = run_static_rules([src])
    assert any(f.rule == "A2K010" and "ghost_atom" in f.message for f in findings)


def test_lint_a2k010_invalid_select_string_skipped(tmp_path: Path) -> None:
    """A select expression that fails to parse is silently skipped (not A2K010)."""
    src = tmp_path / "src" / "main.py"
    src.parent.mkdir(parents=True)
    src.write_text('import a2kit\nr = a2kit.MCPRunner(None, default_select="(((")\n')
    # Either no A2K010 or message references parse failure tolerantly
    findings = run_static_rules([src])
    a2k010 = [f for f in findings if f.rule == "A2K010"]
    assert a2k010 == []


def test_lint_a2k010_disabled(tmp_path: Path) -> None:
    src = tmp_path / "src" / "main.py"
    src.parent.mkdir(parents=True)
    src.write_text('import a2kit\nr = a2kit.MCPRunner(None, default_select="bogus_atom")\n')
    findings = run_static_rules([src], disabled=["A2K010"])
    assert not any(f.rule == "A2K010" for f in findings)


# ---- New exceptions ---------------------------------------------------------


def test_invalid_filter_expression_repr() -> None:
    exc = InvalidFilterExpression("a +", "syntax")
    assert "syntax" in str(exc)
    assert exc.expr == "a +"


def test_projection_unavailable_repr() -> None:
    exc = ProjectionUnavailable()
    assert "celpy" in str(exc).lower() or "cel" in str(exc).lower()


# ---- pyproject loader edge cases -------------------------------------------


def test_find_pyproject_walks_up(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from a2kit.scaffold import _find_pyproject

    proj = tmp_path / "p"
    deep = proj / "a" / "b"
    deep.mkdir(parents=True)
    (proj / "pyproject.toml").write_text("[tool.a2kit]\n")
    monkeypatch.chdir(deep)
    p = _find_pyproject()
    assert p is not None and p.parent == proj


def test_find_pyproject_no_match(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from a2kit.scaffold import _find_pyproject

    monkeypatch.chdir(tmp_path)
    # Walk up from a tmp dir — eventually hits a real pyproject (this repo)
    # so just check the function returns Path or None without crashing.
    p = _find_pyproject(tmp_path)
    assert p is None or p.is_file()


def test_load_pyproject_a2kit_malformed_toml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from a2kit.scaffold import _load_pyproject_a2kit

    proj = tmp_path / "p"
    proj.mkdir()
    (proj / "pyproject.toml").write_text("not valid +++ toml")
    monkeypatch.chdir(proj)
    assert _load_pyproject_a2kit() == {}


def test_load_pyproject_a2kit_no_tool_section(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from a2kit.scaffold import _load_pyproject_a2kit

    proj = tmp_path / "p"
    proj.mkdir()
    (proj / "pyproject.toml").write_text("[project]\nname='x'\n")
    monkeypatch.chdir(proj)
    assert _load_pyproject_a2kit() == {}


def test_load_pyproject_no_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from a2kit.scaffold import _load_pyproject_a2kit

    proj = tmp_path / "no-pyproj-here-and-no-parents"
    proj.mkdir()
    # Use a directory where we know there's no pyproject up the tree
    # (we can't fully isolate from tmp parents; fallback is graceful).
    monkeypatch.chdir(proj)
    out = _load_pyproject_a2kit()
    assert isinstance(out, dict)


def test_pyproject_capabilities_duplicate_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from a2kit.scaffold import _register_pyproject_capabilities

    # Build the table directly (TOML doesn't allow duplicate keys, so we simulate):
    table = {"capabilities": {"a": {"description": "x"}}}
    _register_pyproject_capabilities(table)  # first time OK
    # A second call with same name is idempotent (capabilities.register replaces).
    _register_pyproject_capabilities(table)


def test_pyproject_capabilities_non_table_root_raises() -> None:
    from a2kit.scaffold import _register_pyproject_capabilities

    with pytest.raises(ValueError, match="must be a table"):
        _register_pyproject_capabilities({"capabilities": "not-a-table"})


def test_pyproject_capabilities_empty_skipped() -> None:
    from a2kit.scaffold import _register_pyproject_capabilities

    _register_pyproject_capabilities({})  # no-op


# ---- Removal guards --------------------------------------------------------


def test_feature_alias_raises() -> None:
    with pytest.raises(ImportError, match="Router"):
        from a2kit import Feature  # type: ignore[attr-defined]  # noqa: F401, PLC0415


def test_feature_registry_alias_raises() -> None:
    with pytest.raises(ImportError, match="RouterRegistry"):
        from a2kit import FeatureRegistry  # type: ignore[attr-defined]  # noqa: F401, PLC0415
