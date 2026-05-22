"""Import-discipline rules: fastmcp-import allowlist and package-`__init__` cycle prevention."""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

from a2kit.packages.lint.static import (
    A2K_IMPORT_DISCIPLINE,
    A2K_PKG_INIT_IMPORT,
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
    # codemode subclasses fastmcp's experimental CodeMode transform; the
    # package is imported only by build_mcp_server / serve / the CLI `code`
    # subcommand, so `import a2kit` never pulls fastmcp through it.
    "src/a2kit/packages/codemode/",
    "a2kit/packages/codemode/",
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


def _own_package(filename: str) -> str | None:
    """Dotted name of the file's own package, or ``None`` for a package
    ``__init__.py`` or a path outside an ``a2kit/`` source tree.
    """
    norm = filename.replace("\\", "/")
    if not norm.endswith(".py") or norm.endswith("/__init__.py"):
        return None
    parts = norm.split("/")
    if "a2kit" not in parts:
        return None
    mod_parts = parts[parts.index("a2kit") :]
    mod_parts[-1] = mod_parts[-1][: -len(".py")]
    module = ".".join(mod_parts)
    return module.rsplit(".", 1)[0] if "." in module else module


def rule_pkg_init_import(tree: ast.AST, filename: str, source: str) -> Iterable[LintMessage]:
    """A2K-PKG-INIT-IMPORT — a submodule importing its own package ``__init__``.

    Flags `from a2kit.<...>.<pkg> import ...` and `from . import ...` in any
    non-``__init__`` file under ``src/a2kit/``: both pull the package's own
    ``__init__`` and form a latent import cycle. The fix is to import the
    defining sibling module directly.
    """
    if is_fixture_path(filename):
        return
    package = _own_package(filename)
    if package is None:
        return
    noqa = parse_noqa(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        is_self_absolute = node.level == 0 and node.module == package
        is_self_relative = node.level == 1 and node.module is None
        if not (is_self_absolute or is_self_relative):
            continue
        if suppressed(noqa, A2K_PKG_INIT_IMPORT, node.lineno):
            continue
        yield _msg(
            A2K_PKG_INIT_IMPORT,
            filename,
            node,
            (
                f"submodule imports from its own package `__init__` ({package}); "
                "import the defining sibling module directly to avoid the latent cycle"
            ),
        )


__all__ = ["rule_import_discipline", "rule_pkg_init_import"]
