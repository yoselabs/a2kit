"""A2K-SURFACE-EXPLICIT — credential-named tools SHOULD declare ``surfaces=``.

Fires when a function decorated with ``@a2kit.read``/``write``/``list_``/``tool``
has a name matching a credential-related heuristic AND the decorator call
does NOT pass an explicit ``surfaces=`` kwarg.

The default ``Surface.ALL`` exposes credential-management tools (``login``,
``logout``, etc.) on every transport, including MCP. Agents have no business
calling ``login`` — the plugin author should declare ``surfaces=Surface.CLI``
explicitly (or ``Surface.ALL`` to suppress the lint).

Rule code: ``A2K-SURFACE-EXPLICIT``.
"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

    from a2kit.packages.lint.static import LintMessage


# Conservative heuristic dictionary. Each entry annotated with why it matches.
_CREDENTIAL_NAME_SUBSTRINGS: tuple[str, ...] = (
    "login",  # why: classic credential entry
    "logout",  # why: classic credential teardown
    "signin",  # why: alternate spelling
    "signout",  # why: alternate spelling
    "authenticate",  # why: explicit auth verb
    "set_token",  # why: token write
    "set_credential",  # why: credential write
    "rotate_key",  # why: secret rotation
    "rotate_secret",  # why: secret rotation
    "issue_token",  # why: token mint
    "revoke_token",  # why: token revoke
)

_VERB_NAMES = frozenset({"read", "write", "list_", "tool"})


def _is_a2kit_verb_decorator(dec: ast.expr) -> ast.Call | None:
    """Return the decorator Call node if it's an ``@a2kit.<verb>(...)`` form, else None."""
    if not isinstance(dec, ast.Call):
        return None
    target = dec.func
    if (
        isinstance(target, ast.Attribute)
        and target.attr in _VERB_NAMES
        and isinstance(target.value, ast.Name)
        and target.value.id == "a2kit"
    ):
        return dec
    if isinstance(target, ast.Name) and target.id in _VERB_NAMES:
        return dec
    return None


def _has_surfaces_kwarg(call: ast.Call) -> bool:
    return any(kw.arg == "surfaces" for kw in call.keywords)


def _name_triggers(name: str) -> bool:
    lowered = name.lower()
    return any(token in lowered for token in _CREDENTIAL_NAME_SUBSTRINGS)


def rule_surface_explicit(tree: ast.AST, filename: str, source: str) -> Iterable[LintMessage]:
    """Yield A2K-SURFACE-EXPLICIT findings for the given module AST."""
    del source  # unused; required by signature
    from a2kit.packages.lint.static import A2K_SURFACE_EXPLICIT, LintMessage

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not _name_triggers(node.name):
            continue
        for dec in node.decorator_list:
            call = _is_a2kit_verb_decorator(dec)
            if call is None:
                continue
            if _has_surfaces_kwarg(call):
                continue
            yield LintMessage(
                rule=A2K_SURFACE_EXPLICIT,
                filename=filename,
                line=getattr(dec, "lineno", node.lineno),
                col=getattr(dec, "col_offset", node.col_offset),
                message=(
                    f"tool {node.name!r} defaults to Surface.ALL. Credential-named tools "
                    "SHOULD declare `surfaces=Surface.CLI` explicitly (or `Surface.ALL` "
                    "to suppress)."
                ),
            )


__all__ = ["rule_surface_explicit"]
