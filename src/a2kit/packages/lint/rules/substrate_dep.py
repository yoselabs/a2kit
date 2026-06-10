"""A2K-SUBSTRATE-DEP — forbid FastAPI Depends/Security on MCP-exposed tools.

A parameter typed `Annotated[T, fastapi.params.Depends|Security]` on a tool
whose effective `surfaces=` includes `"mcp"` would fail at build time inside
`install_substrate_signature` with `SubstrateSignatureError`. This rule
promotes that failure to lint time so authors hit it before they ever run.

Tools explicitly scoped `surfaces=("api",)` are exempt — they never reach
the FastMCP substrate.
"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

from a2kit.packages.lint.static import LintMessage, _msg, is_fixture_path, parse_noqa, suppressed

if TYPE_CHECKING:
    from collections.abc import Iterable

A2K_SUBSTRATE_DEP = "AK213"

_MARKER_NAMES = frozenset({"Depends", "Security"})
_VERB_DECORATORS = frozenset({"read", "write", "list_"})


def _is_verb_decorator(node: ast.expr) -> tuple[bool, ast.Call | None]:
    """``True`` if ``node`` looks like an `@a2kit.read|write|list_(...)` call."""
    if not isinstance(node, ast.Call):
        return False, None
    func = node.func
    if isinstance(func, ast.Attribute) and func.attr in _VERB_DECORATORS:
        return True, node
    if isinstance(func, ast.Name) and func.id in _VERB_DECORATORS:
        return True, node
    return False, None


def _surfaces_kwarg(call: ast.Call) -> ast.expr | None:
    for kw in call.keywords:
        if kw.arg == "surfaces":
            return kw.value
    return None


def _dict_mcp_state(value: ast.Dict) -> str | None:
    """Literal state string for the ``"mcp"`` key, ``""`` if the state is
    non-literal, or ``None`` if ``"mcp"`` is absent from the dict."""
    for k, v in zip(value.keys, value.values, strict=False):
        if isinstance(k, ast.Constant) and k.value == "mcp":
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                return v.value
            return ""  # non-literal state
    return None


def _effective_surfaces_include_mcp(call: ast.Call) -> bool:
    """True if the verb is mounted on the MCP surface (so a FastAPI marker leaks).

    No ``surfaces=`` → default LISTED on every surface → mcp included. Tuple/list
    shorthand → ``"mcp"`` among the named (LISTED) surfaces. Dict spelling → an
    ``"mcp"`` entry whose state is not ``"absent"``. Non-literal anything →
    conservatively assume mcp-exposed (the rule cannot prove exclusion).
    """
    value = _surfaces_kwarg(call)
    if value is None:
        return True  # default: LISTED on every surface, mcp included
    if isinstance(value, ast.Tuple | ast.List):
        names = [elt.value for elt in value.elts if isinstance(elt, ast.Constant) and isinstance(elt.value, str)]
        # A non-literal element → cannot prove mcp is excluded → assume exposed.
        return len(names) != len(value.elts) or "mcp" in names
    if isinstance(value, ast.Dict):
        state = _dict_mcp_state(value)
        return state != "absent" if state is not None else False
    return True  # non-literal surfaces= → conservatively assume exposed


def _name_of(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _annotation_carries_marker(ann: ast.expr | None) -> bool:
    """True if `ann` is `Annotated[..., Depends(...)|Security(...), ...]`."""
    if not isinstance(ann, ast.Subscript):
        return False
    if _name_of(ann.value) != "Annotated":
        return False
    elts = ann.slice.elts if isinstance(ann.slice, ast.Tuple) else [ann.slice]
    # Skip the leading type arg; scan the metadata for marker calls.
    return any(isinstance(elt, ast.Call) and _name_of(elt.func) in _MARKER_NAMES for elt in elts[1:])


def _find_verb_call(node: ast.FunctionDef | ast.AsyncFunctionDef) -> ast.Call | None:
    for dec in node.decorator_list:
        ok, call = _is_verb_decorator(dec)
        if ok:
            return call
    return None


def rule_substrate_dep(tree: ast.AST, filename: str, source: str) -> Iterable[LintMessage]:
    if is_fixture_path(filename):
        return
    noqa = parse_noqa(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        verb_call = _find_verb_call(node)
        if verb_call is None or not _effective_surfaces_include_mcp(verb_call):
            continue
        for arg in (*node.args.args, *node.args.kwonlyargs):
            if not _annotation_carries_marker(arg.annotation):
                continue
            if suppressed(noqa, A2K_SUBSTRATE_DEP, node.lineno):
                continue
            yield _msg(
                A2K_SUBSTRATE_DEP,
                filename,
                arg,
                (
                    f"parameter {arg.arg!r} on tool {node.name!r} carries a FastAPI "
                    f"`Depends`/`Security` marker, which cannot appear on MCP-exposed "
                    f"tools. Remove the marker or scope this tool with surfaces=('api',)."
                ),
            )


__all__ = ["A2K_SUBSTRATE_DEP", "rule_substrate_dep"]
