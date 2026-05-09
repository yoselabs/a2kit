"""A2K-LDD-REPORT-TYPE — declaration discipline for ``ctx.report(...)`` calls.

Fires when:
1. A tool body calls ``await ctx.report(...)`` but the verb decorator has no
   ``report=`` kwarg. Encourages explicit declaration; without it, the
   runtime raises ``ReportTypeNotDeclared`` at call time.
2. The declared ``report=ReportT`` type is defined inside a function or class
   body (not at module scope). Pydantic forward-ref resolution constraint —
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
    """Match ``@a2kit.{read,write,list_,tool}`` (with or without call args)."""
    if is_a2kit_tool_decorator(dec):
        return True
    call = dec if isinstance(dec, ast.Call) else None
    target = call.func if call else dec
    if isinstance(target, ast.Attribute):
        return target.attr in _VERB_NAMES and isinstance(target.value, ast.Name) and target.value.id == "a2kit"
    return False


def _verb_decorator_call(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> ast.Call | None:
    for d in fn.decorator_list:
        if _is_a2kit_verb_decorator(d) and isinstance(d, ast.Call):
            return d
    return None


def _has_report_kwarg(call: ast.Call) -> tuple[bool, ast.expr | None]:
    """Return ``(has_kwarg, value_node)`` for ``report=...`` on the decorator."""
    for kw in call.keywords:
        if kw.arg == "report":
            return True, kw.value
    return False, None


def _calls_ctx_report(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.Call]:
    """Find every ``<anything>.report(...)`` call inside ``fn``'s body."""
    matches: list[ast.Call] = []
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "report" and isinstance(func.value, ast.Name):
            # Only flag when the receiver is ``ctx`` (or any var that looks
            # like a ToolContext). We use the param name when present —
            # otherwise the convention is ``ctx``.
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


def rule_ldd_report_type(tree: ast.AST, filename: str, _source: str) -> Iterable[LintMessage]:
    from a2kit.packages.lint.static import A2K_LDD_REPORT_TYPE, LintMessage

    if not isinstance(tree, ast.Module):
        return
    module_names = _module_scope_names(tree)

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        dec_call = _verb_decorator_call(node)
        # Find ctx.report(...) call sites in the body.
        report_calls = _calls_ctx_report(node)

        if dec_call is None:
            # Untagged body with ctx.report → fire on each call site.
            if report_calls and any(_is_a2kit_verb_decorator(d) for d in node.decorator_list):
                for call in report_calls:
                    yield LintMessage(
                        rule=A2K_LDD_REPORT_TYPE,
                        filename=filename,
                        line=call.lineno,
                        col=call.col_offset,
                        message=(
                            "ctx.report(...) called but the verb decorator has no `report=ReportT` kwarg. "
                            "Add `report=YourReportModel` or use ctx.event(...) for free-form narration."
                        ),
                    )
            continue

        has_kw, value_node = _has_report_kwarg(dec_call)

        if report_calls and not has_kw:
            for call in report_calls:
                yield LintMessage(
                    rule=A2K_LDD_REPORT_TYPE,
                    filename=filename,
                    line=call.lineno,
                    col=call.col_offset,
                    message=(
                        "ctx.report(...) called but the verb decorator has no `report=ReportT` kwarg. "
                        "Add `report=YourReportModel` or use ctx.event(...) for free-form narration."
                    ),
                )

        if has_kw and isinstance(value_node, ast.Name) and value_node.id not in module_names:
            yield LintMessage(
                rule=A2K_LDD_REPORT_TYPE,
                filename=filename,
                line=value_node.lineno,
                col=value_node.col_offset,
                message=(
                    f"`report={value_node.id}` references a non-module-scope type. "
                    "Pydantic forward-ref resolution requires module-scope. Hoist the model out."
                ),
            )


__all__ = ["rule_ldd_report_type"]
