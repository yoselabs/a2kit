from __future__ import annotations

import ast
import re
from typing import TYPE_CHECKING

from a2effect import raises_registry
from a2effect._lint._core import LintMessage, collect_raises_names, dotted_name, is_tool_function, iter_functions

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

_DEFECT_OK = re.compile(r"#\s*a2effect:\s*defect-ok\b")


def _source_lines(source: str) -> list[str]:
    return source.splitlines() if source else []


def _line_has_defect_ok(source_lines: list[str], lineno: int) -> bool:
    idx = lineno - 1
    if idx < 0 or idx >= len(source_lines):
        return False
    return bool(_DEFECT_OK.search(source_lines[idx]))


def _is_inside_try(call: ast.Call, fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for node in ast.walk(fn):
        if not isinstance(node, ast.Try):
            continue
        for child in ast.walk(node):
            if child is call:
                # Don't count the except handlers' bodies as "inside try"
                return not any(child is grand for handler in node.handlers for grand in ast.walk(handler))
    return False


def _resolve_call_fq_name(call: ast.Call, imports: dict[str, str]) -> str | None:
    """Best-effort: resolve `client.get` when `from httpx import AsyncClient` and
    `client = AsyncClient()` so the registry key is `httpx.AsyncClient.get`.
    v1 lint takes the trailing dotted attribute chain and falls back to bare name."""
    name = dotted_name(call.func)
    if name is None:
        return None
    head, _, tail = name.partition(".")
    if head in imports:
        return f"{imports[head]}.{tail}" if tail else imports[head]
    return name


def _collect_imports(tree: ast.Module) -> dict[str, str]:
    imports: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            for alias in node.names:
                bound = alias.asname or alias.name
                imports[bound] = f"{node.module}.{alias.name}"
        elif isinstance(node, ast.Import):
            for alias in node.names:
                bound = alias.asname or alias.name
                imports[bound] = alias.name
    return imports


def raises_uncovered_rule(tree: ast.Module, *, path: Path, source: str = "") -> Iterator[LintMessage]:  # noqa: C901
    source_lines = _source_lines(source)
    imports = _collect_imports(tree)
    for fn in iter_functions(tree):
        if not is_tool_function(fn):
            continue
        declared = collect_raises_names(fn.returns)
        for node in ast.walk(fn):
            call: ast.Call | None = None
            if (isinstance(node, ast.Await) and isinstance(node.value, ast.Call)) or (
                isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
            ):
                call = node.value
            if call is None:
                continue
            fq = _resolve_call_fq_name(call, imports)
            if fq is None:
                continue
            registry_raises = raises_registry.get(fq)
            if not registry_raises:
                continue
            uncovered = {r for r in registry_raises if not any(r.endswith(d.rsplit(".", 1)[-1]) for d in declared)}
            if not uncovered:
                continue
            if _is_inside_try(call, fn):
                continue
            if _line_has_defect_ok(source_lines, call.lineno):
                continue
            yield LintMessage(
                rule_id="A2K-RAISES-UNCOVERED",
                severity="warning",
                path=path,
                line=call.lineno,
                col=call.col_offset,
                message=(
                    f"call to {fq} may raise {sorted(uncovered)} not covered by declared raises "
                    f"or try/except; wrap with raises_as / translate_to, add an enricher, "
                    f"or annotate the line with `# a2effect: defect-ok`"
                ),
            )
