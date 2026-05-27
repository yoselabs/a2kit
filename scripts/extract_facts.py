#!/usr/bin/env python
"""extract_facts.py — emit curated codebase facts as JSON for Rego policies.

Walks Python sources, parses each with stdlib ``ast``, and emits a single
JSON document conforming to the schema printable via ``--schema``.

The extractor is a pure function of its input tree: same tree → same JSON,
byte-for-byte. No clock reads, no env reads, no network. Used as the
fact-substrate for ``policies/*.rego``; consumed by ``a2kit lint rego``.

**ast_hash_normalized strategy** (used by ``body_dup.rego``):

Each function's body subtree is normalized:
- ``ast.Name(id=...)`` → ``ast.Name(id="_ID_")``
- ``ast.arg(arg=..., annotation=...)`` → ``ast.arg(arg="_ID_", annotation=None)``
- ``ast.Attribute(attr=...)`` → ``ast.Attribute(attr="_ID_")``
- ``ast.Constant(value=<str|int|float|bytes>)`` → ``ast.Constant(value="_LIT_")``
  (``None`` / ``True`` / ``False`` / ``...`` preserved — semantic distinction)
- ``ast.AnnAssign.annotation`` collapsed to ``_LIT_``
- ``decorator_list`` stripped (decorators are signature, not body)
- ``returns`` stripped (return annotation is signature)

Hash is SHA-256 of ``ast.dump(...)`` of the normalized body module. Two
functions with the same body shape (modulo identifier and literal names)
produce the same hash; functions with different operators / control flow
produce different hashes.

Examples that hash *equal*::

    def f(x): return x + 1
    def g(y): return y + 1       # identifier name differs
    def h(a): return a + 99      # literal value differs

Examples that hash *different*::

    def f(x): return x + 1
    def g(x): return x * 2       # different operator
    def h(x):                    # extra statement
        y = x + 1
        return y

**noqa grammar** (matches ``packages/lint/static.py:parse_noqa``,
commit 83819db):

  ``# noqa: <CODE>[, <CODE>]* [-- <reason text>]``

The separator is exactly ``" -- "`` (space-dash-dash-space). The reason is
free text after.

**REGO-* rules upgrade the convention to required.** A bare ``# noqa:
REGO-*`` without a ``" -- "`` reason raises ``NoqaError`` and the
extractor exits non-zero. Rego policies enforce architectural invariants;
every suppression must be justified inline. A2K-* rules retain the
existing tolerance (reason is conventional, not enforced).
"""

from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

SENTINEL_ID = "_ID_"
SENTINEL_LIT = "_LIT_"

NOQA_PREFIX = "# noqa"
NOQA_REASON_SEP = " -- "
REGO_RULE_PREFIX = "REGO-"

SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "required": ["functions", "modules", "suppressions"],
    "properties": {
        "functions": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "file",
                    "name",
                    "line",
                    "kind",
                    "is_async",
                    "is_private",
                    "is_dunder",
                    "body_stmt_count",
                    "ast_hash_normalized",
                ],
                "properties": {
                    "file": {"type": "string"},
                    "name": {"type": "string"},
                    "line": {"type": "integer"},
                    "kind": {
                        "type": "string",
                        "enum": ["function", "method", "classmethod", "staticmethod"],
                    },
                    "is_async": {"type": "boolean"},
                    "is_private": {"type": "boolean"},
                    "is_dunder": {"type": "boolean"},
                    "body_stmt_count": {"type": "integer"},
                    "ast_hash_normalized": {"type": "string"},
                },
            },
        },
        "modules": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["file", "has_module_getattr"],
                "properties": {
                    "file": {"type": "string"},
                    "has_module_getattr": {"type": "boolean"},
                },
            },
        },
        "suppressions": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["file", "line", "rule_id", "reason"],
                "properties": {
                    "file": {"type": "string"},
                    "line": {"type": "integer"},
                    "rule_id": {"type": "string"},
                    "reason": {"type": "string"},
                },
            },
        },
    },
}


class NoqaError(Exception):
    """REGO-* noqa missing the required ` -- <reason>` suffix."""


# --------------------------------------------------------------------------- #
# AST normalization for body hashing
# --------------------------------------------------------------------------- #


class _Normalizer(ast.NodeTransformer):
    """Replace identifiers + literals with sentinels for body hashing."""

    def visit_Name(self, node: ast.Name) -> ast.AST:
        return ast.Name(id=SENTINEL_ID, ctx=node.ctx)

    def visit_arg(self, node: ast.arg) -> ast.AST:  # noqa: ARG002 -- NodeTransformer interface; we discard the input and return a fresh sentinel node
        return ast.arg(arg=SENTINEL_ID, annotation=None)

    def visit_Attribute(self, node: ast.Attribute) -> ast.AST:
        self.generic_visit(node)
        return ast.Attribute(value=node.value, attr=SENTINEL_ID, ctx=node.ctx)

    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        # None / True / False / Ellipsis are semantic; preserve them
        if node.value is None or isinstance(node.value, bool) or node.value is Ellipsis:
            return node
        return ast.Constant(value=SENTINEL_LIT)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> ast.AST:
        self.generic_visit(node)
        return ast.AnnAssign(
            target=node.target,
            annotation=ast.Constant(value=SENTINEL_LIT),
            value=node.value,
            simple=node.simple,
        )

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        self.generic_visit(node)
        return ast.FunctionDef(
            name=SENTINEL_ID,
            args=node.args,
            body=node.body,
            decorator_list=[],
            returns=None,
            type_params=getattr(node, "type_params", []),
        )

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST:
        self.generic_visit(node)
        return ast.AsyncFunctionDef(
            name=SENTINEL_ID,
            args=node.args,
            body=node.body,
            decorator_list=[],
            returns=None,
            type_params=getattr(node, "type_params", []),
        )


def _strip_docstring(body: list[ast.stmt]) -> list[ast.stmt]:
    """Drop the leading docstring statement if present.

    Two functions with identical logic but different docstring presence
    SHALL hash equal — docstrings are documentation, not behavior.
    """
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, (str, bytes)):
        return body[1:]
    return body


def _count_stmts(body: list[ast.stmt]) -> int:
    """Count statements recursively.

    A single ``try`` block with 5 nested statements counts as 6, not 1.
    The body_dup floor filters trivial 1-2 statement collisions
    (``return x``, ``raise X``); we want substantial bodies wherever
    they're shaped, including nested ones. Top-level stmt counting would
    filter R2 (``resolve_hints`` — single try/except with substantial
    body) as a 1-stmt function, which is wrong for our purposes.
    """
    total = 0
    for stmt in body:
        for _ in ast.walk(stmt):
            # ast.walk yields every node; count only Stmt subtypes
            total += 1 if isinstance(_, ast.stmt) else 0
    return total


def ast_hash_normalized(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """SHA-256 of the function body with identifiers + literals normalized.

    Deep-copies the body before normalizing — the NodeTransformer would
    otherwise mutate the original tree, stripping ``lineno`` from nested
    function definitions and breaking subsequent walks.
    """
    body = _strip_docstring([copy.deepcopy(stmt) for stmt in fn.body])
    normalizer = _Normalizer()
    normalized_body = [normalizer.visit(stmt) for stmt in body]
    body_module = ast.Module(body=normalized_body, type_ignores=[])
    dumped = ast.dump(body_module, annotate_fields=True, include_attributes=False)
    return hashlib.sha256(dumped.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# Function / module / suppression extraction
# --------------------------------------------------------------------------- #


def _function_kind(fn: ast.FunctionDef | ast.AsyncFunctionDef, parent: ast.AST | None) -> str:
    if not isinstance(parent, ast.ClassDef):
        return "function"
    for dec in fn.decorator_list:
        if isinstance(dec, ast.Name):
            if dec.id == "staticmethod":
                return "staticmethod"
            if dec.id == "classmethod":
                return "classmethod"
    return "method"


def extract_functions(tree: ast.Module, filepath: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    def walk(node: ast.AST, parent: ast.AST | None) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = child.name
                is_dunder = name.startswith("__") and name.endswith("__")
                is_private = name.startswith("_") and not is_dunder
                body_stmts = _strip_docstring(child.body)
                out.append(
                    {
                        "file": filepath,
                        "name": name,
                        "line": child.lineno,
                        "kind": _function_kind(child, parent),
                        "is_async": isinstance(child, ast.AsyncFunctionDef),
                        "is_private": is_private,
                        "is_dunder": is_dunder,
                        "body_stmt_count": _count_stmts(body_stmts),
                        "ast_hash_normalized": ast_hash_normalized(child),
                    }
                )
            walk(child, node)

    walk(tree, None)
    return out


def extract_module(tree: ast.Module, filepath: str) -> dict[str, Any]:
    has_module_getattr = False
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "__getattr__":
            has_module_getattr = True
            break
    return {"file": filepath, "has_module_getattr": has_module_getattr}


def extract_suppressions(source: str, filepath: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for lineno, line in enumerate(source.splitlines(), start=1):
        idx = line.find(NOQA_PREFIX)
        if idx == -1:
            continue
        rest = line[idx + len(NOQA_PREFIX) :].lstrip()
        if not rest.startswith(":"):
            # Bare wildcard form (no colon, no codes) — REGO rules don't accept wildcards.
            continue
        payload = rest[1:]
        reason_idx = payload.find(NOQA_REASON_SEP)
        if reason_idx == -1:
            codes_str = payload
            reason = ""
        else:
            codes_str = payload[:reason_idx]
            reason = payload[reason_idx + len(NOQA_REASON_SEP) :].strip()
        codes = [c.strip() for c in codes_str.split(",") if c.strip()]
        for code in codes:
            if code.startswith(REGO_RULE_PREFIX) and not reason:
                raise NoqaError(
                    f"{filepath}:{lineno}: # noqa: {code} requires a reason "
                    f"(grammar: `# noqa: {code} -- <why>`). "
                    f"REGO-* rules enforce architectural invariants — "
                    f"every suppression must be justified inline."
                )
            out.append({"file": filepath, "line": lineno, "rule_id": code, "reason": reason})
    return out


# --------------------------------------------------------------------------- #
# Walk + entrypoint
# --------------------------------------------------------------------------- #


def walk_paths(paths: list[Path]) -> list[Path]:
    out: list[Path] = []
    for p in paths:
        if p.is_dir():
            out.extend(sorted(p.rglob("*.py")))
        elif p.is_file() and p.suffix == ".py":
            out.append(p)
    return out


def extract(paths: list[Path]) -> dict[str, Any]:
    files = walk_paths(paths)
    functions: list[dict[str, Any]] = []
    modules: list[dict[str, Any]] = []
    suppressions: list[dict[str, Any]] = []

    for filepath in files:
        if filepath.name == "extract_facts.py":
            continue
        if "__pycache__" in filepath.parts:
            continue
        try:
            source = filepath.read_text(encoding="utf-8")
        except OSError:
            continue
        try:
            tree = ast.parse(source, filename=str(filepath))
        except SyntaxError:
            continue
        rel = str(filepath)
        functions.extend(extract_functions(tree, rel))
        modules.append(extract_module(tree, rel))
        suppressions.extend(extract_suppressions(source, rel))

    functions.sort(key=lambda d: (d["file"], d["line"], d["name"]))
    modules.sort(key=lambda d: d["file"])
    suppressions.sort(key=lambda d: (d["file"], d["line"], d["rule_id"]))

    return {"functions": functions, "modules": modules, "suppressions": suppressions}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="extract_facts.py",
        description="Walk Python sources and emit curated facts as JSON for Rego policies.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        default=["src/"],
        help="Paths to walk (default: src/).",
    )
    parser.add_argument(
        "--schema",
        action="store_true",
        help="Print the JSON schema of the output and exit.",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="-",
        help="Output path (default: - for stdout).",
    )
    args = parser.parse_args(argv)

    if args.schema:
        json.dump(SCHEMA, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 0

    paths = [Path(p) for p in args.paths]
    try:
        facts = extract(paths)
    except NoqaError as e:
        print(f"extract_facts.py: error: {e}", file=sys.stderr)
        return 2

    text = json.dumps(facts, indent=2, sort_keys=True) + "\n"
    if args.output == "-":
        sys.stdout.write(text)
    else:
        Path(args.output).write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
