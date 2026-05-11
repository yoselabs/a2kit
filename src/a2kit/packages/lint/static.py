"""Static (AST-only) lint dispatch entry for a2kit v1.0.

This module owns:
- ``LintMessage`` finding record
- noqa suppression helpers (``parse_noqa`` / ``suppressed``)
- fixture-path detection (``is_fixture_path``)
- shared rule constants (``BUILTIN_CAPS``, ``ALL_RULES``)
- the per-file dispatch table and ``run_static`` entrypoint

Rule logic lives in ``a2kit.packages.lint.rules.*`` per-family modules.
"""

from __future__ import annotations

import ast
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

# --------------------------------------------------------------------------- #
# Rule codes + shared constants
# --------------------------------------------------------------------------- #

A2K002 = "A2K002"
A2K003 = "A2K003"
A2K006 = "A2K006"
A2K008 = "A2K008"
A2K009 = "A2K009"
A2K011 = "A2K011"
A2K012 = "A2K012"
A2K013 = "A2K013"
A2K014 = "A2K014"

A2K_CONN_LIST_PLACEHOLDER = "A2K-CONN-LIST-PLACEHOLDER"
A2K_IMPORT_DISCIPLINE = "A2K-IMPORT-DISCIPLINE"
A2K_LDD_REPORT_TYPE = "A2K-LDD-REPORT-TYPE"
A2K_LOCAL_RETURN_MODEL = "A2K-LOCAL-RETURN-MODEL"
A2K_CORE_CLEAN = "A2K-CORE-CLEAN"
A2K_EXTRA_NAMESPACE = "A2K-EXTRA-NAMESPACE"
A2K_TEST_MIRROR = "A2K-TEST-MIRROR"
A2K_SURFACE_EXPLICIT = "A2K-SURFACE-EXPLICIT"

ALL_RULES = (
    A2K002,
    A2K003,
    A2K006,
    A2K008,
    A2K009,
    A2K011,
    A2K012,
    A2K013,
    A2K014,
    A2K_CONN_LIST_PLACEHOLDER,
    A2K_IMPORT_DISCIPLINE,
    A2K_LDD_REPORT_TYPE,
    A2K_LOCAL_RETURN_MODEL,
    A2K_CORE_CLEAN,
    A2K_EXTRA_NAMESPACE,
    A2K_TEST_MIRROR,
    A2K_SURFACE_EXPLICIT,
)

BUILTIN_CAPS = frozenset({"read", "write", "destructive", "expensive", "pii", "external"})
_FIXTURE_PATH_TOKENS = ("tests/", "tests\\", "examples/", "examples\\")


# --------------------------------------------------------------------------- #
# LintMessage + suppression helpers
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class LintMessage:
    """Single lint finding from a static rule."""

    rule: str
    filename: str
    line: int
    col: int
    message: str

    def format_concise(self) -> str:
        return f"{self.filename}:{self.line}:{self.col}: {self.rule} {self.message}"


def is_fixture_path(filename: str) -> bool:
    return any(token in filename for token in _FIXTURE_PATH_TOKENS)


def parse_noqa(source: str) -> dict[int, set[str]]:
    out: dict[int, set[str]] = {}
    for i, line in enumerate(source.splitlines(), start=1):
        idx = line.find("# noqa")
        if idx == -1:
            continue
        rest = line[idx + len("# noqa") :].lstrip()
        if rest.startswith(":"):
            codes = {c.strip() for c in rest[1:].split(",") if c.strip()}
            out[i] = codes
        else:
            out[i] = {"*"}
    return out


def suppressed(noqa_map: dict[int, set[str]], rule: str, line: int) -> bool:
    codes = noqa_map.get(line)
    if not codes:
        return False
    return "*" in codes or rule in codes


def _msg(rule: str, filename: str, node: ast.AST, text: str) -> LintMessage:
    return LintMessage(
        rule=rule,
        filename=filename,
        line=getattr(node, "lineno", 1),
        col=getattr(node, "col_offset", 0),
        message=text,
    )


# --------------------------------------------------------------------------- #
# Dispatch table (rule modules imported lazily to avoid circular imports)
# --------------------------------------------------------------------------- #


_RuleFn = Callable[[ast.AST, str, str], Iterable[LintMessage]]


def _build_rules_table() -> tuple[tuple[str, _RuleFn], ...]:
    from a2kit.packages.lint.rules.budget import rule_a2k014
    from a2kit.packages.lint.rules.caps import rule_a2k009, rule_a2k012
    from a2kit.packages.lint.rules.conn import rule_conn_list_placeholder
    from a2kit.packages.lint.rules.importing import rule_import_discipline
    from a2kit.packages.lint.rules.ldd import rule_ldd_report_type
    from a2kit.packages.lint.rules.local_return_model import rule_local_return_model
    from a2kit.packages.lint.rules.mirror import rule_test_mirror
    from a2kit.packages.lint.rules.purity import rule_core_clean, rule_extra_namespace
    from a2kit.packages.lint.rules.shape import rule_a2k002, rule_a2k003, rule_a2k011, rule_a2k013
    from a2kit.packages.lint.rules.surface import rule_surface_explicit

    return (
        (A2K002, rule_a2k002),
        (A2K003, rule_a2k003),
        (A2K009, rule_a2k009),
        (A2K011, rule_a2k011),
        (A2K012, rule_a2k012),
        (A2K013, rule_a2k013),
        (A2K014, rule_a2k014),
        (A2K_CONN_LIST_PLACEHOLDER, rule_conn_list_placeholder),
        (A2K_IMPORT_DISCIPLINE, rule_import_discipline),
        (A2K_LDD_REPORT_TYPE, rule_ldd_report_type),
        (A2K_LOCAL_RETURN_MODEL, rule_local_return_model),
        (A2K_CORE_CLEAN, rule_core_clean),
        (A2K_EXTRA_NAMESPACE, rule_extra_namespace),
        (A2K_TEST_MIRROR, rule_test_mirror),
        (A2K_SURFACE_EXPLICIT, rule_surface_explicit),
    )


def _read_and_parse(path: Path) -> tuple[str, ast.AST] | None:
    try:
        source = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return None
    return source, tree


def run_static_rules(paths: Iterable[Path], *, disabled: Iterable[str] = ()) -> list[LintMessage]:
    """Run all static rules on ``paths``. Returns concatenated findings."""
    from a2kit.packages.lint.rules.cross import (
        collect_param_descriptions,
        collect_router_names,
        collect_tool_names,
        rule_a2k006_cross,
        rule_a2k008_cross,
    )

    rules_table = _build_rules_table()
    disabled_set = set(disabled)
    paths_list = list(paths)
    results: list[LintMessage] = []
    per_file_a2k006: dict[str, dict[str, list[str]]] = {}
    per_file_a2k008: dict[str, tuple[set[str], set[str]]] = {}

    for path in paths_list:
        if path.suffix != ".py":
            continue
        parsed = _read_and_parse(path)
        if parsed is None:
            continue
        source, tree = parsed
        path_str = str(path)
        for code, rule in rules_table:
            if code in disabled_set:
                continue
            results.extend(rule(tree, path_str, source))
        if A2K006 not in disabled_set:
            per_file_a2k006[path_str] = collect_param_descriptions(tree)
        if A2K008 not in disabled_set and not is_fixture_path(path_str):
            per_file_a2k008[path_str] = (collect_router_names(tree), collect_tool_names(tree))

    if A2K006 not in disabled_set:
        results.extend(rule_a2k006_cross(per_file_a2k006))
    if A2K008 not in disabled_set:
        results.extend(rule_a2k008_cross(per_file_a2k008))

    return results


# Public alias for v1.0 surface.
run_static = run_static_rules


__all__ = [
    "A2K002",
    "A2K003",
    "A2K006",
    "A2K008",
    "A2K009",
    "A2K011",
    "A2K012",
    "A2K013",
    "A2K014",
    "A2K_CONN_LIST_PLACEHOLDER",
    "A2K_CORE_CLEAN",
    "A2K_EXTRA_NAMESPACE",
    "A2K_IMPORT_DISCIPLINE",
    "A2K_LDD_REPORT_TYPE",
    "A2K_LOCAL_RETURN_MODEL",
    "A2K_SURFACE_EXPLICIT",
    "A2K_TEST_MIRROR",
    "ALL_RULES",
    "BUILTIN_CAPS",
    "LintMessage",
    "is_fixture_path",
    "parse_noqa",
    "run_static",
    "run_static_rules",
    "suppressed",
]
