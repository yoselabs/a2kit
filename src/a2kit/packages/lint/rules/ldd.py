"""A2K-LDD-REPORT-TYPE — declaration discipline for ``ctx.report(...)`` calls.

Fires when:
1. A tool body calls ``await ctx.report(...)`` but the verb decorator has
   no ``reports=ReportT`` kwarg. Without it, the runtime raises
   ``ReportTypeNotDeclared`` at call time.
2. The declared report type is defined inside a function or class body
   (not at module scope). Pydantic forward-ref resolution constraint —
   mirrors A2K003 / ANTIPATTERNS entry on Pydantic return types.

Rule code: ``A2K-LDD-REPORT-TYPE``.
"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

from a2kit.packages.lint.rules import is_a2kit_tool_decorator

if TYPE_CHECKING:
    from collections.abc import Iterable

    from a2kit.packages.lint.static import LintMessage

_VERB_NAMES = {"read", "write", "list_", "tool"}


def _is_a2kit_verb_decorator(dec: ast.expr) -> bool:
    if is_a2kit_tool_decorator(dec):
        return True
    call = dec if isinstance(dec, ast.Call) else None
    target = call.func if call else dec
    if isinstance(target, ast.Attribute):
        return target.attr in _VERB_NAMES and isinstance(target.value, ast.Name) and target.value.id == "a2kit"
    return False


def _reports_kwarg(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> ast.keyword | None:
    """Match ``reports=ReportT`` kwarg on a verb decorator call."""
    for d in fn.decorator_list:
        if not isinstance(d, ast.Call):
            continue
        if not _is_a2kit_verb_decorator(d):
            continue
        for kw in d.keywords:
            if kw.arg == "reports":
                return kw
    return None


def _calls_ctx_report(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.Call]:
    matches: list[ast.Call] = []
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "report" and isinstance(func.value, ast.Name):
            matches.append(node)
    return matches


def _module_scope_names(tree: ast.Module) -> set[str]:  # noqa: C901
    out: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            out.add(node.name)
        elif isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    out.add(tgt.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            out.add(node.target.id)
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                out.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                out.add((alias.asname or alias.name).split(".")[0])
    return out


def _has_a2kit_verb_decorator(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return any(_is_a2kit_verb_decorator(d) for d in fn.decorator_list)


def rule_ldd_report_type(tree: ast.AST, filename: str, _source: str) -> Iterable[LintMessage]:
    from a2kit.packages.lint.static import A2K_LDD_REPORT_TYPE, LintMessage

    if not isinstance(tree, ast.Module):
        return
    module_names = _module_scope_names(tree)

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not _has_a2kit_verb_decorator(node):
            continue

        report_calls = _calls_ctx_report(node)
        reports_kw = _reports_kwarg(node)

        if report_calls and reports_kw is None:
            for call in report_calls:
                yield LintMessage(
                    rule=A2K_LDD_REPORT_TYPE,
                    filename=filename,
                    line=call.lineno,
                    col=call.col_offset,
                    message=(
                        "ctx.report(...) called but no `reports=ReportT` kwarg on the verb decorator. "
                        "Add `reports=YourReportModel` to @a2kit.read/write/list_/tool, or use "
                        "ctx.event(...) for free-form narration."
                    ),
                )

        if reports_kw is not None:
            arg = reports_kw.value
            if isinstance(arg, ast.Name) and arg.id not in module_names:
                yield LintMessage(
                    rule=A2K_LDD_REPORT_TYPE,
                    filename=filename,
                    line=arg.lineno,
                    col=arg.col_offset,
                    message=(
                        f"`reports={arg.id}` references a non-module-scope type. "
                        "Pydantic forward-ref resolution requires module-scope. Hoist the model out."
                    ),
                )


__all__ = ["rule_ldd_report_type"]
