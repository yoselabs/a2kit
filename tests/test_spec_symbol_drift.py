"""SPEC ↔ live-code parity gate.

Spec-tree sibling of ``tests/test_readme_symbol_drift.py`` and
``tests/test_docs_symbol_drift.py``. Scans every ``openspec/specs/*/spec.md``
and asserts that each *checkable* code-font symbol resolves on the live
``a2kit`` surface — binding against the imported types, not text-matching
``src/``.

The extraction + resolution engine lives in ``tests/support/symbol_drift.py``
(shared with the docs gate); this module supplies the spec file set and the
spec-specific allowlist.

See ADR 0018 and the ``spec-drift-gate`` capability. The allowlist holds only
tombstone-migration targets, logger names, and illustrative placeholders — no
grandfathered drift. A symbol that does not resolve is a spec to fix, not an
allowlist entry to add.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.support.symbol_drift import collect_drift

SPECS_DIR = Path(__file__).resolve().parent.parent / "openspec" / "specs"

# Structurally a2kit-shaped symbols that legitimately do not resolve.
# Two groups only: tombstone-migration targets (a spec may cite a
# removed name in a REMOVED requirement's migration line) and
# illustrative placeholders (pattern-description metavariables). The
# grandfathered-drift group is empty — reconcile-spec-drift-residual
# cleared every `# reconcile:` entry. A new entry here is a red flag:
# fix the spec, do not allowlist live drift.
_ALLOWLIST: frozenset[str] = frozenset(
    {
        # --- tombstone migration targets: a spec cites a removed name to
        #     document its migration; not resolving is the point ---
        "a2kit.AppBuilder",  # removed in the one-App collapse (ADR 0017)
        "a2kit.tool",  # removed v0.33 — split into read/write/list_ verbs
        "Container.dispatch",  # renamed to call_scope (d1dddb7); the spec
        # scenario cites the absent symbol as proof the rename is loud
        "a2kit.packages.dispatch.substrate.Substrate",  # removed in
        # remove-substrate-literal; surface-protocol spec cites it in the
        # migration-hint scenario
        "App.debug",  # removed in di-for-sub-configs (2026-05-25); the
        "app.debug",  # core-composition + runtime-config specs cite the
        # name in their tombstone / migration-hint paragraphs.
        # --- example-only / illustrative placeholders cited in pattern
        #     descriptions (not real surface, not drift) ---
        "App.method",  # illustrative metavariable in docs-code-parity
        "Router.attribute",  # illustrative metavariable in docs-code-parity
        "a2kit.log.foo",  # illustrative metavariable in docs-code-parity
        "app.method",  # illustrative metavariable in docs-code-parity
        # --- a2effect-foundation lint rules: spec-declared, runtime
        #     implementation deferred to a2lint-extraction follow-up. The
        #     specs name them now to lock the contract; the live registry
        #     gains them when a2lint-extraction lands. ---
        "A2K-RAISES-CLOSURE",
        "A2K-RAISES-UNCOVERED",
        "A2K-RAISES-NOT-TYPED",
        "A2K-RAISES-HELPER-UNTYPED",
        "A2K-OUTPUT-SCHEMA-COMPAT",
        # ruff-`noqa`-grammar-safe renames of the deferred raises rules
        # (ruff-compatible-lint-codes). Same deferral: the live registry
        # gains them when a2lint-extraction / a2effect lands.
        "AK220",  # = legacy A2K-RAISES-CLOSURE
        "AK221",  # = legacy A2K-RAISES-UNCOVERED
        "AK222",  # = legacy A2K-RAISES-NOT-TYPED
        "AK22",  # prose family token from `AK22x` (the AK22-series glob)
        # --- illustrative example codes cited in pattern descriptions,
        #     not registered rules (lint-code-format `e.g.` lists) ---
        "RG010",  # `e.g. RG001, RG002, RG010` — illustrative RG example
        # --- string names cited in scenarios (logger names, span attrs)
        #     that look like dotted import paths but are not ---
        "a2kit.log.sink_failed",  # logger name for the WARN-log on sink failures (refounded a2kit.ldd -> a2kit.log)
        "a2kit.calls",  # dedicated non-streaming logger name for the call-log (call-log capability)
        "a2kit.dur_ms",  # OTel span attribute name
        # --- Rego data-namespace paths (policies/data.json keys, NOT Python
        #     imports). The `rego-policy-layer` spec quotes them as
        #     `a2kit.allowlist.<policy>` — they live in OPA's data tree, not
        #     in the Python package surface. ---
        "a2kit.allowlist.body_dup",
        "a2kit.allowlist.name_collision",
        "a2kit.allowlist.github_actions_vendor",
        "a2kit.allowlist.github_actions_vendor_unpinned",
        "a2kit.allowlist.pyproject_upper_bound",
    }
)


def _collect_drift(text: str, *, label: str) -> list[tuple[str, int, str]]:
    """Spec-gate binding of the shared engine with the spec allowlist."""
    return collect_drift(text, label=label, allowlist=_ALLOWLIST)


# --- BDD: the gate's own behaviour ---------------------------------------- #


def test_dead_dotted_symbol_is_caught() -> None:
    drift = _collect_drift("A spec citing `a2kit.NonexistentThing` here.", label="fixture")
    assert drift, "a dead dotted a2kit symbol must fail the gate"
    assert "a2kit.NonexistentThing" in drift[0][0]


def test_dead_canonical_access_is_caught() -> None:
    drift = _collect_drift("The old `Container._totally_fake_seam` seam.", label="fixture")
    assert drift, "a dead Container attribute access must fail the gate"
    assert "Container._totally_fake_seam" in drift[0][0]


def test_dead_lint_rule_code_is_caught() -> None:
    drift = _collect_drift("Enforced by `A2K-NONEXISTENT-RULE` at lint time.", label="fixture")
    assert drift, "a dead A2K- lint-rule code must fail the gate"
    assert "A2K-NONEXISTENT-RULE" in drift[0][0]


def test_allowlisted_name_passes() -> None:
    drift = _collect_drift("Migrate off `a2kit.AppBuilder` per ADR 0017.", label="fixture")
    assert drift == [], "an allowlisted tombstone target must not fail the gate"


def test_illustrative_tokens_are_not_checked() -> None:
    drift = _collect_drift("Use `Lazy[T]` or `pydantic.Field` or `dict[str, int]`.", label="fixture")
    assert drift == [], "type-annotation fragments and third-party tokens are not checkable"


def test_live_symbols_pass() -> None:
    drift = _collect_drift("Construct `a2kit.App`, call `app.provide`, see `A2K-LAYER`.", label="fixture")
    assert drift == [], f"live symbols must resolve, got: {drift}"


# --- the gate ------------------------------------------------------------- #


def test_all_spec_symbols_resolve_in_live_code() -> None:
    """Every checkable symbol in every capability spec resolves in src/a2kit/."""
    spec_files = sorted(SPECS_DIR.glob("*/spec.md"))
    assert spec_files, f"no spec files found under {SPECS_DIR}"

    drift: list[tuple[str, int, str]] = []
    for spec in spec_files:
        rel = spec.relative_to(SPECS_DIR.parent.parent)
        drift.extend(_collect_drift(spec.read_text(encoding="utf-8"), label=str(rel)))

    if drift:
        lines = "\n".join(f"  {entry}" for entry, _, _ in drift)
        pytest.fail(
            "Capability specs cite symbols that do not resolve on the live a2kit "
            "surface. Fix the spec, or allowlist the symbol in "
            "tests/test_spec_symbol_drift.py:\n" + lines
        )
