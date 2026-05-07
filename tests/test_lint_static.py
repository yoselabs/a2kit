"""Tests for a2kit.lint.static — A2K001..A2K006 + run_static_rules."""

from __future__ import annotations

import ast
from pathlib import Path

from a2kit.lint._common import LintMessage, parse_noqa, suppressed
from a2kit.lint.static import (
    A2K001,
    A2K002,
    A2K003,
    A2K004,
    A2K005,
    A2K006,
    rule_a2k001,
    rule_a2k002,
    rule_a2k003,
    rule_a2k004,
    rule_a2k005,
    run_static_rules,
)


def _parse(code: str) -> tuple[ast.AST, str]:
    return ast.parse(code), code


def test_a2k001_flags_missing_connection_param() -> None:
    code = """
import a2kit
@a2kit.tool(connection_param="conn")
def f(x: str) -> dict:
    return {}
"""
    tree, src = _parse(code)
    msgs = list(rule_a2k001(tree, "f.py", src))
    assert len(msgs) == 1
    assert msgs[0].rule == A2K001


def test_a2k001_passes_when_param_present() -> None:
    code = """
import a2kit
@a2kit.tool(connection_param="conn")
def f(conn: str) -> dict:
    return {}
"""
    tree, src = _parse(code)
    assert list(rule_a2k001(tree, "f.py", src)) == []


def test_a2k001_handles_bare_name_decorator() -> None:
    code = """
from a2kit import tool
@tool(connection_param="conn")
def f(x: str) -> dict:
    return {}
"""
    tree, src = _parse(code)
    msgs = list(rule_a2k001(tree, "f.py", src))
    assert msgs and msgs[0].rule == A2K001


def test_a2k001_skips_when_connection_param_not_constant() -> None:
    code = """
import a2kit
NAME = "conn"
@a2kit.tool(connection_param=NAME)
def f(x: str) -> dict:
    return {}
"""
    tree, src = _parse(code)
    assert list(rule_a2k001(tree, "f.py", src)) == []


def test_a2k001_respects_noqa() -> None:
    code = """
import a2kit
@a2kit.tool(connection_param="conn")
def f(x: str) -> dict:  # noqa: A2K001
    return {}
"""
    tree, src = _parse(code)
    assert list(rule_a2k001(tree, "f.py", src)) == []


def test_a2k002_flags_str_return_on_a2kit_tool() -> None:
    code = """
import a2kit
@a2kit.tool()
def f() -> str:
    return ""
"""
    tree, src = _parse(code)
    msgs = list(rule_a2k002(tree, "f.py", src))
    assert msgs and msgs[0].rule == A2K002


def test_a2k002_flags_str_return_on_server_tool() -> None:
    code = """
@server.tool()
def f() -> str:
    return ""
"""
    tree, src = _parse(code)
    msgs = list(rule_a2k002(tree, "f.py", src))
    assert msgs and msgs[0].rule == A2K002


def test_a2k002_str_string_annotation() -> None:
    code = """
import a2kit
@a2kit.tool()
def f() -> "str":
    return ""
"""
    tree, src = _parse(code)
    msgs = list(rule_a2k002(tree, "f.py", src))
    assert msgs and msgs[0].rule == A2K002


def test_a2k002_passes_dict_return() -> None:
    code = """
import a2kit
@a2kit.tool()
def f() -> dict:
    return {}
"""
    tree, src = _parse(code)
    assert list(rule_a2k002(tree, "f.py", src)) == []


def test_a2k002_skips_no_return() -> None:
    code = """
import a2kit
@a2kit.tool()
def f():
    return {}
"""
    tree, src = _parse(code)
    assert list(rule_a2k002(tree, "f.py", src)) == []


def test_a2k003_flags_local_pydantic_return() -> None:
    code = """
from pydantic import BaseModel
import a2kit

class Out(BaseModel):
    x: int

@a2kit.tool()
def f() -> Out:
    return Out(x=1)
"""
    tree, src = _parse(code)
    msgs = list(rule_a2k003(tree, "f.py", src))
    assert msgs and msgs[0].rule == A2K003


def test_a2k003_skips_test_paths() -> None:
    """A2K003 short-circuits on test/example files."""
    code = """
from pydantic import BaseModel
import a2kit
class Out(BaseModel):
    x: int
@a2kit.tool()
def f() -> Out:
    return Out(x=1)
"""
    tree, src = _parse(code)
    assert list(rule_a2k003(tree, "tests/test_x.py", src)) == []


def test_a2k004_skips_test_paths() -> None:
    """A2K004 short-circuits on test/example files."""
    code = """
import a2kit
@a2kit.tool(connection_param="connection")
def f(connection: str) -> dict:
    return {}
"""
    tree, src = _parse(code)
    assert list(rule_a2k004(tree, "examples/foo.py", src)) == []


def test_a2k003_skips_when_no_local_models() -> None:
    code = """
import a2kit
@a2kit.tool()
def f() -> dict:
    return {}
"""
    tree, src = _parse(code)
    assert list(rule_a2k003(tree, "f.py", src)) == []


def test_a2k003_skips_non_tool() -> None:
    code = """
from pydantic import BaseModel
class Out(BaseModel):
    x: int
def f() -> Out:
    return Out(x=1)
"""
    tree, src = _parse(code)
    assert list(rule_a2k003(tree, "f.py", src)) == []


def test_a2k004_flags_missing_doc_helper() -> None:
    code = '''
import a2kit
@a2kit.tool(connection_param="connection")
def f(connection: str) -> dict:
    """No mention of the helper."""
    return {}
'''
    tree, src = _parse(code)
    msgs = list(rule_a2k004(tree, "f.py", src))
    assert msgs and msgs[0].rule == A2K004


def test_a2k004_skips_when_helper_referenced() -> None:
    code = '''
import a2kit
@a2kit.tool(connection_param="connection")
def f(connection: str) -> dict:
    """Use connection_param_doc()."""
    return {}
'''
    tree, src = _parse(code)
    assert list(rule_a2k004(tree, "f.py", src)) == []


def test_a2k005_flags_legacy_key_fields() -> None:
    """v0.5: any leftover `KEY_FIELDS = ...` becomes a migration error."""
    code = """
import a2kit
class Conn(a2kit.ConnectionInfo):
    KEY_FIELDS = ("project", "env", "db")
"""
    tree, src = _parse(code)
    msgs = list(rule_a2k005(tree, "f.py", src))
    assert any(m.rule == A2K005 and "legacy" in m.message for m in msgs)


def test_a2k005_flags_legacy_ann_assign() -> None:
    code = """
import a2kit
class Conn(a2kit.ConnectionInfo):
    KEY_FIELDS: tuple[str, ...] = ("project", "env")
"""
    tree, src = _parse(code)
    msgs = list(rule_a2k005(tree, "f.py", src))
    assert any(m.rule == A2K005 and "legacy" in m.message for m in msgs)


def test_a2k005_passes_namedtuple_key() -> None:
    code = """
from typing import NamedTuple
import a2kit
class WidgetKey(NamedTuple):
    project: str
    env: str
    db: str
class Conn(a2kit.ConnectionInfo, key=WidgetKey):
    pass
"""
    tree, src = _parse(code)
    assert list(rule_a2k005(tree, "f.py", src)) == []


def test_a2k005_skips_classes_without_key_fields() -> None:
    code = """
import a2kit
class Conn(a2kit.ConnectionInfo):
    pass
"""
    tree, src = _parse(code)
    assert list(rule_a2k005(tree, "f.py", src)) == []


def test_a2k005_noqa_suppresses() -> None:
    code = """
import a2kit
class Conn(a2kit.ConnectionInfo):  # noqa: A2K005
    KEY_FIELDS = ("Bad",)
"""
    tree, src = _parse(code)
    assert list(rule_a2k005(tree, "f.py", src)) == []


def test_a2k006_cross_file_dedup(tmp_path: Path) -> None:
    text = '''
import a2kit
@a2kit.tool()
def t1(filter_expr: str) -> dict:
    """filter_expr: A JMESPath expression filtering results in a stable way."""
    return {}
'''
    files = []
    for i in range(3):
        p = tmp_path / f"m{i}.py"
        p.write_text(text)
        files.append(p)
    msgs = run_static_rules(files)
    assert any(m.rule == A2K006 for m in msgs)


def test_run_static_rules_skips_syntax_errors(tmp_path: Path) -> None:
    bad = tmp_path / "bad.py"
    bad.write_text("def f(:\n")
    msgs = run_static_rules([bad])
    assert msgs == []


def test_run_static_rules_skips_unreadable(tmp_path: Path) -> None:
    msgs = run_static_rules([tmp_path / "missing.py"])
    assert msgs == []


def test_a2k001_skips_non_a2kit_decorators() -> None:
    """A function with only `@server.tool()` (not a2kit) is skipped by A2K001."""
    code = """
@server.tool()
def f(x: str) -> dict:
    return {}
"""
    tree, src = _parse(code)
    assert list(rule_a2k001(tree, "f.py", src)) == []


def test_a2k003_non_name_return_annotation() -> None:
    """`-> Mapping[str, int]` — return annotation is a Subscript, not a Name."""
    code = """
from pydantic import BaseModel
from typing import Mapping
import a2kit
class Out(BaseModel):
    pass
@a2kit.tool()
def f() -> Mapping[str, int]:
    return {}
"""
    tree, src = _parse(code)
    assert list(rule_a2k003(tree, "f.py", src)) == []


def test_a2k004_noqa_suppresses() -> None:
    code = """
import a2kit
@a2kit.tool(connection_param="connection")
def f(connection: str) -> dict:  # noqa: A2K004
    return {}
"""
    tree, src = _parse(code)
    assert list(rule_a2k004(tree, "f.py", src)) == []


def test_a2k006_two_files_below_threshold(tmp_path: Path) -> None:
    """Same description in 2 files (< 3) produces no finding (covers `< 3` branch)."""
    text = '''
import a2kit
@a2kit.tool()
def t(filter_expr: str) -> dict:
    """filter_expr: A JMESPath expression filtering results in a stable way."""
    return {}
'''
    files = []
    for i in range(2):
        p = tmp_path / f"m{i}.py"
        p.write_text(text)
        files.append(p)
    msgs = run_static_rules(files)
    assert all(m.rule != A2K006 for m in msgs)


def test_a2k006_skips_short_descriptions(tmp_path: Path) -> None:
    """Descriptions < 20 chars and non-identifier names are filtered out."""
    text = '''
import a2kit
@a2kit.tool()
def t(x: int) -> dict:
    """x: short.
    not a docline at all
    """
    return {}
'''
    files = []
    for i in range(3):
        p = tmp_path / f"m{i}.py"
        p.write_text(text)
        files.append(p)
    msgs = run_static_rules(files)
    # No A2K006 finding because `short` < 20 chars.
    assert all(m.rule != A2K006 for m in msgs)


def test_run_static_rules_a2k006_disabled(tmp_path: Path) -> None:
    """When A2K006 is disabled, _collect_param_descriptions is skipped."""
    p = tmp_path / "m.py"
    p.write_text("x = 1\n")
    msgs = run_static_rules([p], disabled=["A2K006"])
    assert msgs == []


def test_run_static_rules_disabled_codes(tmp_path: Path) -> None:
    p = tmp_path / "f.py"
    p.write_text(
        """
import a2kit
@a2kit.tool()
def f() -> str:
    return ""
"""
    )
    msgs = run_static_rules([p], disabled=["A2K002"])
    assert all(m.rule != A2K002 for m in msgs)


def test_lint_message_format() -> None:
    m = LintMessage(rule="A2K001", filename="x.py", line=3, col=0, message="hello")
    assert m.format_concise() == "x.py:3:0: A2K001 hello"


def test_parse_noqa_blanket_and_specific() -> None:
    src = "x = 1  # noqa\ny = 2  # noqa: A2K001, A2K002\n"
    out = parse_noqa(src)
    assert out[1] == {"*"}
    assert out[2] == {"A2K001", "A2K002"}


def test_suppressed_blanket() -> None:
    assert suppressed({1: {"*"}}, "A2K001", 1)
    assert not suppressed({}, "A2K001", 1)
    assert suppressed({1: {"A2K001"}}, "A2K001", 1)
    assert not suppressed({1: {"A2K002"}}, "A2K001", 1)
