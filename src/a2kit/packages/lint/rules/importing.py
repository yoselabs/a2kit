"""Import-discipline rules: fastmcp allowlist, package-`__init__` cycles, layer DAG, front doors."""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

from a2kit.packages.lint.layers import (
    FACADE_MODULES,
    FOUNDATIONAL_CORE_MODULES,
    layer_of,
    unit_for_module,
    unit_for_path,
)
from a2kit.packages.lint.static import (
    A2K_IMPORT_DISCIPLINE,
    A2K_LAYER,
    A2K_PKG_FRONT_DOOR,
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
    # `run_code` (behind the CLI `code` subcommand) wraps the MCP server in a
    # `fastmcp.Client`; the import is function-local so the cold path is
    # unaffected.
    "src/a2kit/packages/cli/_serve.py",
    "a2kit/packages/cli/_serve.py",
    # The stderr ToolContext mirrors fastmcp.Context's elicitation result
    # types; the import is lazy (inside ctx.elicit()), so importing a2kit
    # alone never pulls fastmcp.
    "src/a2kit/packages/context/",
    "a2kit/packages/context/",
    # otel adapter subclasses fastmcp.server.middleware.Middleware; lazy-loaded
    # via packages.otel.install() so cold-start budget is unaffected.
    "src/a2kit/packages/otel/",
    "a2kit/packages/otel/",
    # codemode subclasses fastmcp's experimental CodeMode transform; the
    # package is imported only by build_mcp_server / serve, so `import a2kit`
    # never pulls fastmcp through it.
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


#: Documented allowlist for A2K-PKG-FRONT-DOOR — deliberate deep
#: cross-package imports. Empty by default; every entry needs a comment
#: and is a full dotted module path.
_FRONT_DOOR_ALLOWLIST: tuple[str, ...] = ()


def rule_pkg_front_door(tree: ast.AST, filename: str, source: str) -> Iterable[LintMessage]:
    """A2K-PKG-FRONT-DOOR — a cross-package import must target the package
    front door (``a2kit.packages.X``), not a deep submodule.

    ADR 0004 declares ``a2kit.packages.X.__init__`` the front door; this
    rule makes it the *only* door. Importing ``a2kit.packages.X.<sub>``
    from outside package ``X`` is flagged. A submodule importing a
    sibling inside its own package is fine (that is internal wiring).
    """
    if is_fixture_path(filename):
        return
    norm = filename.replace("\\", "/")
    if "a2kit/" not in norm:
        return
    if any(norm.endswith(facade) for facade in FACADE_MODULES):
        return
    own = unit_for_path(filename)
    noqa = parse_noqa(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.level != 0:
            continue
        mod = node.module or ""
        parts = mod.split(".")
        if len(parts) < 4 or parts[0] != "a2kit" or parts[1] != "packages":
            continue
        target_pkg = parts[2]
        if target_pkg == own:
            continue
        if mod in _FRONT_DOOR_ALLOWLIST:
            continue
        if suppressed(noqa, A2K_PKG_FRONT_DOOR, node.lineno):
            continue
        yield _msg(
            A2K_PKG_FRONT_DOOR,
            filename,
            node,
            (
                f"deep import `{mod}` reaches past package `{target_pkg}`'s front door; "
                f"import the public name from `a2kit.packages.{target_pkg}` instead"
            ),
        )


def _layer_import_targets(node: ast.AST) -> list[str]:
    """Dotted module names an import node references (``[]`` for non-imports)."""
    if isinstance(node, ast.ImportFrom):
        if node.level != 0 or not node.module:
            return []
        return [node.module]
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    return []


def collect_layer_imports(
    tree: ast.AST,
    filename: str,
    source: str,
) -> tuple[str | None, list[tuple[str, int, bool]]]:
    """Collect this file's a2kit import edges for the A2K-LAYER cross check.

    Returns ``(own_unit, edges)`` where each edge is
    ``(target_unit, lineno, suppressed)``. Returns ``(None, [])`` for
    files that do not participate in layering — ``__init__.py`` re-export
    boundaries, the public-facade modules in ``LAYER_EXEMPT_FILES``, and
    fixture paths. Walks every ``ImportFrom`` / ``Import`` node, so
    ``TYPE_CHECKING``-guarded and function-local imports are included.
    """
    norm = filename.replace("\\", "/")
    if is_fixture_path(filename) or "a2kit/" not in norm or norm.endswith("/__init__.py"):
        return None, []
    if any(norm.endswith(facade) for facade in FACADE_MODULES):
        return None, []
    own = unit_for_path(filename)
    if own is None:
        return None, []
    noqa = parse_noqa(source)
    edges: list[tuple[str, int, bool]] = []
    for node in ast.walk(tree):
        targets = _layer_import_targets(node)
        if not targets:
            continue
        lineno = getattr(node, "lineno", 1)
        supp = suppressed(noqa, A2K_LAYER, lineno)
        for mod in targets:
            if mod in FOUNDATIONAL_CORE_MODULES:
                continue
            target_unit = unit_for_module(mod)
            if target_unit is None or target_unit == own:
                continue
            edges.append((target_unit, lineno, supp))
    return own, edges


def _unit_graph(
    per_file: dict[str, tuple[str | None, list[tuple[str, int, bool]]]],
) -> dict[str, set[str]]:
    """Build the unit -> {imported units} graph from collected edges."""
    graph: dict[str, set[str]] = {}
    for own, edges in per_file.values():
        if own is None:
            continue
        graph.setdefault(own, set())
        for target_unit, _lineno, _supp in edges:
            graph[own].add(target_unit)
            graph.setdefault(target_unit, set())
    return graph


def _reachable(graph: dict[str, set[str]], start: str) -> set[str]:
    """Every unit reachable from ``start`` (transitive closure)."""
    seen: set[str] = set()
    stack = list(graph.get(start, ()))
    while stack:
        node = stack.pop()
        if node in seen:
            continue
        seen.add(node)
        stack.extend(graph.get(node, ()))
    return seen


def _layer_finding(
    filename: str,
    own: str,
    target_unit: str,
    lineno: int,
    target_reach: set[str],
) -> LintMessage | None:
    """The A2K-LAYER finding for one import edge, or ``None`` when clean."""
    own_layer = layer_of(own)
    target_layer = layer_of(target_unit)
    if own_layer is not None and target_layer is not None and target_layer > own_layer:
        return LintMessage(
            rule=A2K_LAYER,
            filename=filename,
            line=lineno,
            col=0,
            message=(
                f"`{own}` (layer {own_layer}) imports `{target_unit}` (layer {target_layer}) — a unit may import only strictly-lower layers"
            ),
        )
    if own in target_reach:
        return LintMessage(
            rule=A2K_LAYER,
            filename=filename,
            line=lineno,
            col=0,
            message=(f"`{own}` imports `{target_unit}`, which transitively imports `{own}` back — this closes an import cycle"),
        )
    return None


def rule_a2k_layer_cross(
    per_file: dict[str, tuple[str | None, list[tuple[str, int, bool]]]],
) -> list[LintMessage]:
    """A2K-LAYER cross-file check: higher-layer imports and import cycles.

    Resolves every import to its layer-manifest unit. A unit may import
    only strictly-lower layers (plus its own). A same-layer import that
    closes a cycle — the importer transitively reachable from the import
    target — is flagged too.
    """
    graph = _unit_graph(per_file)
    reach: dict[str, set[str]] = {}
    results: list[LintMessage] = []
    for filename, (own, edges) in per_file.items():
        if own is None:
            continue
        for target_unit, lineno, supp in edges:
            if supp:
                continue
            if target_unit not in reach:
                reach[target_unit] = _reachable(graph, target_unit)
            finding = _layer_finding(filename, own, target_unit, lineno, reach[target_unit])
            if finding is not None:
                results.append(finding)
    return results


__all__ = [
    "collect_layer_imports",
    "rule_a2k_layer_cross",
    "rule_import_discipline",
    "rule_pkg_front_door",
    "rule_pkg_init_import",
]
