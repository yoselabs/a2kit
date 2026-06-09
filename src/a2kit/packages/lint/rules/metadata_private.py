"""A2K-METADATA-PRIVATE — guard the private `_get_meta` / `_set_meta` surface.

`a2kit.metadata._get_meta` and `_set_meta` are composition-time helpers used
by the verb decorators and a handful of core modules. Reading tool data
elsewhere SHALL go through `ToolDescriptor` (via `AppRuntime.descriptor_for`
or `App.tools()`). Importing the underscored names outside the allowlist is
a hard error.
"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

from a2kit.packages.lint.static import LintMessage, _msg, is_fixture_path, parse_noqa, suppressed

if TYPE_CHECKING:
    from collections.abc import Iterable

A2K_METADATA_PRIVATE = "AK210"

_METADATA_PRIVATE_ALLOWLIST = frozenset(
    {
        "a2kit._verbs",
        "a2kit.metadata",
        "a2kit.runtime",
        "a2kit.tool",
        "a2kit.app",
        "a2kit.routers",
        "a2kit.schema",
    }
)

_GUARDED_NAMES = frozenset({"_get_meta", "_set_meta"})


def _own_module(filename: str) -> str | None:
    norm = filename.replace("\\", "/")
    if not norm.endswith(".py"):
        return None
    parts = norm.split("/")
    if "a2kit" not in parts:
        return None
    mod_parts = parts[parts.index("a2kit") :]
    mod_parts[-1] = mod_parts[-1][: -len(".py")]
    if mod_parts[-1] == "__init__":
        mod_parts = mod_parts[:-1]
    return ".".join(mod_parts)


def rule_metadata_private(tree: ast.AST, filename: str, source: str) -> Iterable[LintMessage]:
    if is_fixture_path(filename):
        return
    own = _own_module(filename)
    if own is None:
        return
    if own in _METADATA_PRIVATE_ALLOWLIST:
        return
    noqa = parse_noqa(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.level != 0 or node.module != "a2kit.metadata":
            continue
        leaked = sorted(alias.name for alias in node.names if alias.name in _GUARDED_NAMES)
        if not leaked:
            continue
        if suppressed(noqa, A2K_METADATA_PRIVATE, node.lineno):
            continue
        yield _msg(
            A2K_METADATA_PRIVATE,
            filename,
            node,
            (
                f"`{own}` imports private metadata helper(s) {leaked} from `a2kit.metadata`; "
                "read tool data via `ToolDescriptor` (e.g. `runtime.descriptor_for(name)._meta` "
                "or `descriptor.metadata_view`). Allowlist: " + ", ".join(sorted(_METADATA_PRIVATE_ALLOWLIST))
            ),
        )


__all__ = ["A2K_METADATA_PRIVATE", "rule_metadata_private"]
