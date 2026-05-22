"""A2K-TEST-MIRROR — every source file has a mirror test file.

For each `src/a2kit/<path>/<file>.py` (excluding allow-listed files),
this rule asserts that `tests/<path>/test_<file>.py` exists and contains
at least one `def test_*` function. The rule fires only on source paths
under `src/a2kit/`; non-source paths short-circuit.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import TYPE_CHECKING

from a2kit.packages.lint.static import LintMessage

if TYPE_CHECKING:
    from collections.abc import Iterable

A2K_TEST_MIRROR = "A2K-TEST-MIRROR"

# why: each entry has no testable behavior beyond what the mirror rule
# would mechanically demand. Documented inline; revisit if the file
# acquires real logic.
ALLOW_LIST: frozenset[str] = frozenset(
    {
        # why: frozen dataclass; construction-only, covered indirectly.
        "src/a2kit/metadata.py",
        # why: covered by tests/packages/cli/test_field_to_typer.py (the
        # mirror rule expects the leading-underscore form to match the
        # source filename; the existing test file uses the no-underscore
        # form because it exercises both the public and private surface).
        "src/a2kit/packages/cli/_field_to_typer.py",
        # why: schema generation is tested end-to-end through tool
        # registration and CLI/MCP schema commands; no isolated tests.
        "src/a2kit/schema.py",
        # why: pure helpers extracted from a2kit/app.py to keep app.py
        # under the SLOC budget; behavior covered by
        # tests/test_singleton_type_inference.py +
        # tests/test_singleton_lifecycle_detection.py.
        "src/a2kit/_lifecycle_helpers.py",
        # why: pure helpers extracted from a2kit/packages/di/container.py
        # to keep container.py under the SLOC budget; behavior covered
        # end-to-end through every singleton/provider test that exercises
        # the DI container.
        "src/a2kit/packages/di/_introspection.py",
        # why: ``@a2kit.list_`` annotation helpers extracted from
        # a2kit/tool.py to keep tool.py under the SLOC budget; behavior
        # covered by tests/test_list_verb.py / tests/test_verb_annotations.py.
        "src/a2kit/_list_helpers.py",
        # why: verb-decorator bodies (``read`` / ``write`` / ``list_`` /
        # ``_read_internal`` + helpers) extracted from a2kit/tool.py per
        # tidy-v035-deferred-items so tool.py drops the A2K014 suppression;
        # behavior covered by tests/test_verb_annotations.py,
        # tests/test_list_verb.py, tests/test_timeout_decorator.py,
        # tests/test_audit_loud_failure.py, tests/test_decoration_warn_once.py.
        "src/a2kit/_verbs.py",
        # why: pure introspection helpers for the verb decorators
        # (return-shape validators + reserved-name guards) extracted
        # from _verbs.py per tidy-review-followups to give _verbs.py
        # headroom under the A2K014 SLOC budget; behavior covered
        # indirectly through every verb-decorated tool's stamp call
        # and the decoration-warn-once tests.
        "src/a2kit/_verb_validators.py",
        # why: per-scope LIFO cleanup stack tested via
        # tests/packages/di/test_cleanup_stack.py (single-underscore
        # naming predates the mirror rule's double-underscore expectation).
        "src/a2kit/packages/di/_cleanup_stack.py",
        # why: `resolve_hints` wrapper tested via tests/test_resolve_hints.py;
        # behavior also exercised through every signature-introspecting test.
        "src/a2kit/packages/di/_hints.py",
        # why: pure type alias `Lazy = Callable[[], Awaitable[T]]` — no
        # runtime behavior to test in isolation; consumers exercise it in
        # tests/packages/di/test_lazy_annotation.py + 3 wire/CLI tests.
        "src/a2kit/packages/di/_lazy.py",
        # why: `Scope` enum with two constants; constants exercised by
        # every per-call/app-scope test under tests/packages/di/.
        "src/a2kit/packages/di/scope.py",
        # why: `Resolver` Protocol tested via
        # tests/packages/di/test_resolver_protocol.py (the test name
        # describes what's pinned — the Protocol shape — rather than
        # mirroring the source filename).
        "src/a2kit/packages/di/resolver.py",
        # why: MCP dispatch-wrapper chain extracted from
        # a2kit/packages/mcp/server.py to keep server.py under the A2K014
        # SLOC budget; behavior covered end-to-end by every test under
        # tests/packages/mcp/ plus tests/test_operational_contracts.py
        # (error envelope) and tests/test_decoration_warn_once.py.
        "src/a2kit/packages/mcp/_wrappers.py",
        # why: `serve` / `code` CLI subcommand registration extracted from
        # a2kit/packages/cli/builder.py to keep builder.py under the A2K014
        # SLOC budget; behavior covered by tests/packages/mcp/test_cli.py
        # and tests/packages/codemode/test_cli_code.py.
        "src/a2kit/packages/cli/_serve.py",
    }
)

_TEST_ONLY_MANIFEST = Path("tests/_test_only.txt")


def _normalize(path: str) -> str:
    return path.replace("\\", "/")


def _is_init_or_main(filename: str) -> bool:
    leaf = filename.rsplit("/", 1)[-1]
    return leaf in {"__init__.py", "__main__.py"}


def source_to_mirror(source_path: str) -> str | None:
    """Map a `src/a2kit/...` path to its `tests/.../test_<leaf>.py` mirror.

    Returns ``None`` for any path outside ``src/a2kit/``.
    """
    norm = _normalize(source_path)
    if not norm.startswith("src/a2kit/"):
        return None
    if not norm.endswith(".py"):
        return None
    rel = norm[len("src/a2kit/") :]
    parent, _, leaf = rel.rpartition("/")
    mirror_leaf = f"test_{leaf}"
    return f"tests/{parent}/{mirror_leaf}" if parent else f"tests/{mirror_leaf}"


def _mirror_has_test_function(mirror_path: Path) -> bool:
    try:
        source = mirror_path.read_text(encoding="utf-8")
    except OSError:
        return False
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name.startswith("test_"):
            return True
    return False


def load_test_only_manifest() -> frozenset[str]:
    """Load the `tests/_test_only.txt` catalog of test-only files.

    Lines starting with ``#`` and blanks are ignored. Paths are
    normalized to forward-slash form.
    """
    if not _TEST_ONLY_MANIFEST.exists():
        return frozenset()
    out: set[str] = set()
    for raw in _TEST_ONLY_MANIFEST.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        out.add(_normalize(stripped))
    return frozenset(out)


def _is_allow_listed(source_path: str) -> bool:
    norm = _normalize(source_path)
    if _is_init_or_main(norm):
        return True
    return norm in ALLOW_LIST


def rule_test_mirror(_tree: ast.AST, filename: str, _source: str) -> Iterable[LintMessage]:
    """Fire when a non-exempt `src/a2kit/` file lacks a populated mirror."""
    norm = _normalize(filename)
    if not norm.startswith("src/a2kit/"):
        return
    if _is_allow_listed(norm):
        return
    mirror = source_to_mirror(norm)
    if mirror is None:
        return
    mirror_path = Path(mirror)
    if not mirror_path.exists():
        yield LintMessage(
            rule=A2K_TEST_MIRROR,
            filename=filename,
            line=1,
            col=0,
            message=f"missing mirror test file: expected {mirror}",
        )
        return
    if not _mirror_has_test_function(mirror_path):
        yield LintMessage(
            rule=A2K_TEST_MIRROR,
            filename=filename,
            line=1,
            col=0,
            message=f"mirror {mirror} has no `def test_*` function",
        )


__all__ = [
    "A2K_TEST_MIRROR",
    "ALLOW_LIST",
    "load_test_only_manifest",
    "rule_test_mirror",
    "source_to_mirror",
]
