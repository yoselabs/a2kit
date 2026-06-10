"""DOCS ↔ live-code parity gate.

Living-narrative-doc sibling of ``tests/test_readme_symbol_drift.py`` and
``tests/test_spec_symbol_drift.py``. Scans the human-readable docs that teach
the current public surface and asserts every checkable code-font symbol
resolves on the live ``a2kit`` surface — so a rename/removal in code fails at
PR time rather than at consumer-migration time (the exact rot that left
``a2kit.ldd.*`` strewn through these docs after the stdlib-logging refounding).

The extraction + resolution engine lives in ``tests/support/symbol_drift.py``
(shared with the spec gate); this module supplies the doc set and the
doc-specific allowlist.

**Scope.** Current-state docs only: ``ANTIPATTERNS.md``,
``OPERATIONAL_CONTRACTS.md``, and ``docs/patterns/*.md``. ``docs/adr/*.md`` is
DELIBERATELY EXCLUDED — an ADR is a historical record and rightly cites the
names it removed; gating it would punish correct history.

The allowlist holds only genuine non-symbols (logger *names*, OTel span
attributes). A symbol that does not resolve is a doc to fix, not an allowlist
entry to add.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.support.symbol_drift import collect_drift

_ROOT = Path(__file__).resolve().parent.parent

#: Current-state living docs under the gate. ADR bodies are excluded by design.
DOC_FILES: list[Path] = [
    _ROOT / "ANTIPATTERNS.md",
    _ROOT / "OPERATIONAL_CONTRACTS.md",
    *sorted((_ROOT / "docs" / "patterns").glob("*.md")),
]

# Structurally a2kit-shaped tokens that legitimately do not resolve — genuine
# non-symbols only (logger names, span attributes). NOT a home for stale
# examples: a reference to a removed API is a doc to fix, not to allowlist.
_ALLOWLIST: frozenset[str] = frozenset(
    {
        # --- string names cited in prose that look like dotted import paths
        #     but are getLogger() names, not Python attributes ---
        "a2kit.di.cleanup",  # logger name for the WARN-log on DI cleanup failures
        "a2kit.log.sink_failed",  # logger name for the WARN-log on handler failures
        "a2kit.calls",  # dedicated non-streaming logger name for the call-log
        # --- sentinel marker strings that lint rule AK013 greps for in tool
        #     docstrings (shape.py::_A2K013_MARKERS) — string literals, not
        #     importable symbols ---
        "a2kit.docs.connection_param_doc",
        "a2kit.docs.param_doc",
    }
)


def test_all_doc_symbols_resolve_in_live_code() -> None:
    """Every checkable symbol in every living narrative doc resolves in src/a2kit/."""
    present = [p for p in DOC_FILES if p.exists()]
    assert present, f"no living-narrative docs found under {_ROOT}"

    drift: list[tuple[str, int, str]] = []
    for doc in present:
        rel = doc.relative_to(_ROOT)
        drift.extend(collect_drift(doc.read_text(encoding="utf-8"), label=str(rel), allowlist=_ALLOWLIST))

    if drift:
        lines = "\n".join(f"  {entry}" for entry, _, _ in drift)
        pytest.fail(
            "Living docs cite symbols that do not resolve on the live a2kit "
            "surface. Fix the doc to match the code (NO backward-compat), or — "
            "only for a genuine non-symbol (a logger name) — allowlist it in "
            "tests/test_docs_symbol_drift.py:\n" + lines
        )
