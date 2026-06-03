"""Static (AST-only) lint dispatch entry for a2kit v1.0.

This module owns:
- ``LintMessage`` finding record
- noqa suppression helpers (``parse_noqa`` / ``suppressed``)
- fixture-path detection (``is_fixture_path``)
- shared rule constants (``BUILTIN_CAPS``, ``ALL_RULES``)
- the per-file dispatch table and ``run_static_rules`` entrypoint

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
A2K011 = "A2K011"
A2K013 = "A2K013"
A2K014 = "A2K014"
A2K015 = "A2K015"  # _ensure() lazy-init pattern (di-scoped-lifecycle anti-pattern)
A2K016 = "A2K016"  # parameterized lambda as DI factory
A2K017 = "A2K017"  # Lazy[T] suggestion for conditional-use deps

A2K_CONN_LIST_PLACEHOLDER = "A2K-CONN-LIST-PLACEHOLDER"
A2K_IMPORT_DISCIPLINE = "A2K-IMPORT-DISCIPLINE"
A2K_PKG_INIT_IMPORT = "A2K-PKG-INIT-IMPORT"  # submodule importing its own package __init__
A2K_PKG_INIT_IMPL = "A2K-PKG-INIT-IMPL"  # implementation defined in a package __init__
A2K_PKG_INIT_PURITY = "A2K-PKG-INIT-PURITY"  # package __init__ does not re-export `_`-prefixed names
A2K_LAYER = "A2K-LAYER"  # import-graph layer DAG (manifest in packages/lint/layers.py)
A2K_PKG_FRONT_DOOR = "A2K-PKG-FRONT-DOOR"  # cross-package imports target the package __init__
A2K_LOCAL_RETURN_MODEL = "A2K-LOCAL-RETURN-MODEL"
A2K_EXTRA_NAMESPACE = "A2K-EXTRA-NAMESPACE"
A2K_TEST_MIRROR = "A2K-TEST-MIRROR"
A2K_SURFACE_EXPLICIT = "A2K-SURFACE-EXPLICIT"
A2K_SURFACE_REGISTRY = "A2K-SURFACE-REGISTRY"  # Surface subclass without MANIFEST
A2K_METADATA_PRIVATE = "A2K-METADATA-PRIVATE"
A2K_SUBSTRATE_DEP = "A2K-SUBSTRATE-DEP"
A2K_NO_DICT_STR_ANY = "A2K-NO-DICT-STR-ANY"  # dict[str, Any] on internal dataclass field

ALL_RULES = (
    A2K002,
    A2K003,
    A2K006,
    A2K008,
    A2K011,
    A2K013,
    A2K014,
    A2K015,
    A2K016,
    A2K017,
    A2K_CONN_LIST_PLACEHOLDER,
    A2K_IMPORT_DISCIPLINE,
    A2K_PKG_INIT_IMPORT,
    A2K_PKG_INIT_IMPL,
    A2K_PKG_INIT_PURITY,
    A2K_LAYER,
    A2K_PKG_FRONT_DOOR,
    A2K_LOCAL_RETURN_MODEL,
    A2K_EXTRA_NAMESPACE,
    A2K_TEST_MIRROR,
    A2K_SURFACE_EXPLICIT,
    A2K_SURFACE_REGISTRY,
    A2K_METADATA_PRIVATE,
    A2K_SUBSTRATE_DEP,
    A2K_NO_DICT_STR_ANY,
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
            payload = rest[1:]
            # Strip optional `-- reason` suffix (e.g. `# noqa: A2K001 -- why`).
            reason_idx = payload.find(" -- ")
            if reason_idx != -1:
                payload = payload[:reason_idx]
            codes = {c.strip() for c in payload.split(",") if c.strip()}
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
    from a2kit.packages.lint.rules.conn import rule_conn_list_placeholder
    from a2kit.packages.lint.rules.di_scoped import (
        rule_ensure_pattern,
        rule_lazy_t_suggestion,
        rule_parameterized_lambda_factory,
    )
    from a2kit.packages.lint.rules.importing import (
        rule_import_discipline,
        rule_pkg_front_door,
        rule_pkg_init_impl,
        rule_pkg_init_import,
        rule_pkg_init_purity,
    )
    from a2kit.packages.lint.rules.local_return_model import rule_local_return_model
    from a2kit.packages.lint.rules.metadata_private import rule_metadata_private
    from a2kit.packages.lint.rules.mirror import rule_test_mirror
    from a2kit.packages.lint.rules.no_dict_str_any import rule_no_dict_str_any
    from a2kit.packages.lint.rules.purity import rule_extra_namespace
    from a2kit.packages.lint.rules.shape import rule_a2k002, rule_a2k003, rule_a2k011, rule_a2k013
    from a2kit.packages.lint.rules.substrate_dep import rule_substrate_dep
    from a2kit.packages.lint.rules.surface import rule_surface_explicit
    from a2kit.packages.lint.rules.surface_registry import rule_surface_registry

    return (
        (A2K002, rule_a2k002),
        (A2K003, rule_a2k003),
        (A2K011, rule_a2k011),
        (A2K013, rule_a2k013),
        (A2K014, rule_a2k014),
        (A2K015, rule_ensure_pattern),
        (A2K016, rule_parameterized_lambda_factory),
        (A2K017, rule_lazy_t_suggestion),
        (A2K_CONN_LIST_PLACEHOLDER, rule_conn_list_placeholder),
        (A2K_IMPORT_DISCIPLINE, rule_import_discipline),
        (A2K_PKG_INIT_IMPORT, rule_pkg_init_import),
        (A2K_PKG_INIT_IMPL, rule_pkg_init_impl),
        (A2K_PKG_INIT_PURITY, rule_pkg_init_purity),
        (A2K_PKG_FRONT_DOOR, rule_pkg_front_door),
        (A2K_LOCAL_RETURN_MODEL, rule_local_return_model),
        (A2K_EXTRA_NAMESPACE, rule_extra_namespace),
        (A2K_TEST_MIRROR, rule_test_mirror),
        (A2K_SURFACE_EXPLICIT, rule_surface_explicit),
        (A2K_SURFACE_REGISTRY, rule_surface_registry),
        (A2K_METADATA_PRIVATE, rule_metadata_private),
        (A2K_SUBSTRATE_DEP, rule_substrate_dep),
        (A2K_NO_DICT_STR_ANY, rule_no_dict_str_any),
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


def run_static_rules(paths: Iterable[Path], *, disabled: Iterable[str] = ()) -> list[LintMessage]:  # noqa: C901 -- per-file dispatch loop with per-rule + cross-rule branches
    """Run all static rules on ``paths``. Returns concatenated findings."""
    from a2kit.packages.lint.rules.cross import (
        collect_param_descriptions,
        collect_router_names,
        collect_tool_names,
        rule_a2k006_cross,
        rule_a2k008_cross,
    )
    from a2kit.packages.lint.rules.importing import collect_layer_imports, rule_a2k_layer_cross

    rules_table = _build_rules_table()
    disabled_set = set(disabled)
    paths_list = list(paths)
    results: list[LintMessage] = []
    per_file_a2k006: dict[str, dict[str, list[str]]] = {}
    per_file_a2k008: dict[str, tuple[set[str], set[str]]] = {}
    per_file_layer: dict[str, tuple[str | None, list[tuple[str, int, bool]]]] = {}

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
        if A2K_LAYER not in disabled_set:
            per_file_layer[path_str] = collect_layer_imports(tree, path_str, source)

    if A2K006 not in disabled_set:
        results.extend(rule_a2k006_cross(per_file_a2k006))
    if A2K008 not in disabled_set:
        results.extend(rule_a2k008_cross(per_file_a2k008))
    if A2K_LAYER not in disabled_set:
        results.extend(rule_a2k_layer_cross(per_file_layer))

    return results


__all__ = [
    "A2K002",
    "A2K003",
    "A2K006",
    "A2K008",
    "A2K011",
    "A2K013",
    "A2K014",
    "A2K_CONN_LIST_PLACEHOLDER",
    "A2K_EXTRA_NAMESPACE",
    "A2K_IMPORT_DISCIPLINE",
    "A2K_LAYER",
    "A2K_LOCAL_RETURN_MODEL",
    "A2K_NO_DICT_STR_ANY",
    "A2K_PKG_FRONT_DOOR",
    "A2K_PKG_INIT_IMPL",
    "A2K_PKG_INIT_IMPORT",
    "A2K_SURFACE_EXPLICIT",
    "A2K_TEST_MIRROR",
    "ALL_RULES",
    "BUILTIN_CAPS",
    "LintMessage",
    "is_fixture_path",
    "parse_noqa",
    "run_static_rules",
    "suppressed",
]
