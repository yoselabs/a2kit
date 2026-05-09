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
        # why: ToolContext Protocol — pure interface, no implementation.
        "src/a2kit/runtime.py",
        # why: frozen dataclass; construction-only, covered indirectly.
        "src/a2kit/metadata.py",
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
