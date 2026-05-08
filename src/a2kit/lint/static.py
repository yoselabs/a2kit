"""Static (AST-only) lint rules orchestrator.

Each rule lives in a `_rules_*.py` module:

- `_rules_returns.py`      — A2K002, A2K003, A2K011  (return-annotation shape)
- `_rules_capabilities.py` — A2K009, A2K012          (raw cap strings)
- `_rules_docs.py`         — A2K006, A2K013          (docstring patterns)
- `_rules_collisions.py`   — A2K008, A2K010          (cross-file collisions)
- `_rules_size.py`         — A2K014                  (file-size budget)

This module wires them together. No imports are executed during analysis.
Cross-tool / cross-file rules walk multiple files in `run_static_rules`.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import TYPE_CHECKING

from a2kit.lint._common import (
    A2K002,
    A2K003,
    A2K006,
    A2K008,
    A2K009,
    A2K010,
    A2K011,
    A2K012,
    A2K013,
    A2K014,
    ALL_RULES,
    is_fixture_path,
)
from a2kit.lint._rules_capabilities import rule_a2k009, rule_a2k012
from a2kit.lint._rules_collisions import (
    collect_router_names,
    collect_select_strings_from_source,
    collect_tool_names,
    resolve_known_atoms_from_files,
    rule_a2k008_cross,
    rule_a2k010,
    scan_pyproject_select,
    scan_shell_select_strings,
)
from a2kit.lint._rules_docs import collect_param_descriptions, rule_a2k006_cross, rule_a2k013
from a2kit.lint._rules_returns import rule_a2k002, rule_a2k003, rule_a2k011
from a2kit.lint._rules_size import rule_a2k014

if TYPE_CHECKING:
    from collections.abc import Iterable

    from a2kit.lint._common import LintMessage


__all__ = [
    "A2K002",
    "A2K003",
    "A2K006",
    "A2K008",
    "A2K009",
    "A2K010",
    "A2K011",
    "A2K012",
    "A2K013",
    "A2K014",
    "ALL_RULES",
    "run_static_rules",
]


_RULES_PER_FILE = (
    (A2K002, rule_a2k002),
    (A2K003, rule_a2k003),
    (A2K009, rule_a2k009),
    (A2K011, rule_a2k011),
    (A2K012, rule_a2k012),
    (A2K013, rule_a2k013),
    (A2K014, rule_a2k014),
)


def _read_and_parse(path: Path) -> tuple[str, ast.AST] | None:
    """Read+parse a Python source file. Return None on read/parse error."""
    try:
        source = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return None
    return source, tree


def _run_per_file_rules(
    tree: ast.AST,
    path_str: str,
    source: str,
    disabled_set: set[str],
) -> Iterable[LintMessage]:
    """Run every per-file static rule that isn't disabled."""
    for code, rule in _RULES_PER_FILE:
        if code in disabled_set:
            continue
        yield from rule(tree, path_str, source)


def _accumulate_cross_file_state(
    path: Path,
    tree: ast.AST,
    disabled_set: set[str],
    per_file_a2k006: dict[str, dict[str, list[str]]],
    per_file_a2k008: dict[str, tuple[set[str], set[str]]],
    select_findings: list[tuple[Path, ast.AST, str]],
) -> None:
    """Collect cross-file inputs (A2K006/A2K008/A2K010) for one source tree."""
    path_str = str(path)
    if A2K006 not in disabled_set:
        per_file_a2k006[path_str] = collect_param_descriptions(tree)
    if A2K008 not in disabled_set and not is_fixture_path(path_str):
        per_file_a2k008[path_str] = (collect_router_names(tree), collect_tool_names(tree))
    if A2K010 not in disabled_set and not is_fixture_path(path_str):
        for n, value in collect_select_strings_from_source(tree):
            select_findings.append((path, n, value))


def _run_cross_file_rules(
    paths_list: list[Path],
    disabled_set: set[str],
    per_file_a2k006: dict[str, dict[str, list[str]]],
    per_file_a2k008: dict[str, tuple[set[str], set[str]]],
    select_findings: list[tuple[Path, ast.AST, str]],
    shell_findings: list[tuple[Path, int, str]],
) -> Iterable[LintMessage]:
    """Emit findings for the cross-file rules (A2K006, A2K008, A2K010)."""
    if A2K006 not in disabled_set:
        yield from rule_a2k006_cross(per_file_a2k006)
    if A2K008 not in disabled_set:
        yield from rule_a2k008_cross(per_file_a2k008)
    if A2K010 not in disabled_set:
        known_atoms = resolve_known_atoms_from_files(per_file_a2k008)
        anchor = paths_list[0] if paths_list else Path.cwd()
        pyproject_select = scan_pyproject_select(anchor if anchor.is_dir() else anchor.parent)
        yield from rule_a2k010(pyproject_select, select_findings, shell_findings, known_atoms)


def run_static_rules(paths: Iterable[Path], *, disabled: Iterable[str] = ()) -> list[LintMessage]:
    """Run all static rules on `paths`. Returns concatenated findings."""
    disabled_set = set(disabled)
    paths_list = list(paths)
    results: list[LintMessage] = []
    per_file_a2k006: dict[str, dict[str, list[str]]] = {}
    per_file_a2k008: dict[str, tuple[set[str], set[str]]] = {}
    select_findings: list[tuple[Path, ast.AST, str]] = []
    shell_findings = scan_shell_select_strings(paths_list)

    for path in paths_list:
        if path.suffix != ".py":
            continue
        parsed = _read_and_parse(path)
        if parsed is None:
            continue
        source, tree = parsed
        results.extend(_run_per_file_rules(tree, str(path), source, disabled_set))
        _accumulate_cross_file_state(path, tree, disabled_set, per_file_a2k006, per_file_a2k008, select_findings)

    results.extend(
        _run_cross_file_rules(
            paths_list,
            disabled_set,
            per_file_a2k006,
            per_file_a2k008,
            select_findings,
            shell_findings,
        ),
    )
    return results
