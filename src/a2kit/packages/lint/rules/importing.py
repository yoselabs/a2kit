"""Import-discipline rule.

- A2K-IMPORT-DISCIPLINE — ``fastmcp`` imports outside the allowlist.
"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

from a2kit.packages.lint.static import (
    A2K_IMPORT_DISCIPLINE,
    LintMessage,
    _msg,
    is_fixture_path,
    parse_noqa,
    suppressed,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

_FASTMCP_ALLOWLIST = (
    "src/a2kit/packages/mcp/",
    "a2kit/packages/mcp/",
    "src/a2kit/packages/cli/builder.py",
    "a2kit/packages/cli/builder.py",
    # CLI stub mirrors fastmcp.Context's elicitation result types; the import
    # is lazy (inside ctx.elicit()), so importing a2kit alone never pulls fastmcp.
    "src/a2kit/packages/cli/context.py",
    "a2kit/packages/cli/context.py",
    # otel adapter subclasses fastmcp.server.middleware.Middleware; lazy-loaded
    # via packages.otel.install() so cold-start budget is unaffected.
    "src/a2kit/packages/otel/",
    "a2kit/packages/otel/",
)


def _path_is_allowlisted_for_fastmcp(filename: str) -> bool:
    norm = filename.replace("\\", "/")
    return any(norm.endswith(suffix.rstrip("/")) or (suffix.endswith("/") and suffix in norm) for suffix in _FASTMCP_ALLOWLIST)


def rule_import_discipline(tree: ast.AST, filename: str, source: str) -> Iterable[LintMessage]:
    if is_fixture_path(filename):
        return
    norm = filename.replace("\\", "/")
    if "a2kit/" not in norm:
        return
    if _path_is_allowlisted_for_fastmcp(filename):
        return
    noqa = parse_noqa(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if not (mod == "fastmcp" or mod.startswith("fastmcp.")):
                continue
        elif isinstance(node, ast.Import):
            if not any(alias.name == "fastmcp" or alias.name.startswith("fastmcp.") for alias in node.names):
                continue
        else:
            continue
        if suppressed(noqa, A2K_IMPORT_DISCIPLINE, node.lineno):
            continue
        yield _msg(
            A2K_IMPORT_DISCIPLINE,
            filename,
            node,
            (
                "fastmcp imports must be confined to `packages/mcp/` (and the lazy import inside "
                "`packages/cli/builder.py`'s `serve` subcommand). Cold-start budget allows it nowhere else."
            ),
        )


__all__ = ["rule_import_discipline"]
