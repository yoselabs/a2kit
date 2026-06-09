"""ruff-compatible-lint-codes (ADR 0028 orthogonal) — code-shape + grammar.

a2kit lint codes must fit ruff's `# noqa` grammar `[A-Z]+[0-9]+` under reserved
vendor prefixes (`AK` static, `AKR` runtime, `RG` rego) so a2kit codes and ruff
codes co-suppress on one line without either parser breaking. A frozen
`LEGACY_CODE_ALIASES` table resolves old dashed/`A2K###` codes during the
deprecation window; emitted findings always carry the new code.
"""

from __future__ import annotations

import re

import pytest

RUFF_CODE = re.compile(r"^[A-Z]+[0-9]+$")


def _all_a2kit_codes() -> set[str]:
    from a2kit.packages.lint.runtime import ALL_CHECKS
    from a2kit.packages.lint.static import ALL_RULES

    rego = _rego_codes()
    return set(ALL_RULES) | set(ALL_CHECKS) | rego


def _rego_codes() -> set[str]:
    """The rego rule-IDs the alias table maps to (RG family)."""
    from a2kit.packages.lint.static import LEGACY_CODE_ALIASES

    return {new for old, new in LEGACY_CODE_ALIASES.items() if new.startswith("RG")}


# --------------------------------------------------------------------------- #
# §1.1 — every code matches the ruff noqa grammar.
# --------------------------------------------------------------------------- #


def test_every_code_is_ruff_noqa_shaped() -> None:
    bad = sorted(c for c in _all_a2kit_codes() if not RUFF_CODE.match(c))
    assert bad == [], f"non-ruff-grammar lint codes: {bad}"


# --------------------------------------------------------------------------- #
# §1.2 — reserved prefixes are disjoint, no cross-family code collision.
# --------------------------------------------------------------------------- #


def test_reserved_prefixes_disjoint_and_codes_unique() -> None:
    from a2kit.packages.lint.runtime import ALL_CHECKS
    from a2kit.packages.lint.static import ALL_RULES

    static = set(ALL_RULES)
    runtime = set(ALL_CHECKS)
    rego = _rego_codes()

    # Prefix discipline: static = AK (not AKR), runtime = AKR, rego = RG.
    assert all(c.startswith("AK") and not c.startswith("AKR") for c in static), static
    assert all(c.startswith("AKR") for c in runtime), runtime
    assert all(c.startswith("RG") for c in rego), rego

    # No code is defined in two families.
    assert static.isdisjoint(runtime)
    assert static.isdisjoint(rego)
    assert runtime.isdisjoint(rego)

    # No duplicate within the union.
    union = list(ALL_RULES) + list(ALL_CHECKS) + sorted(rego)
    assert len(union) == len(set(union)), "a code is defined twice"


# --------------------------------------------------------------------------- #
# §2.1 — parse_noqa accepts new prefixes; foreign ruff codes pass through.
# --------------------------------------------------------------------------- #


def test_parse_noqa_mixed_a2kit_and_ruff_line() -> None:
    from a2kit.packages.lint.static import parse_noqa, suppressed

    src = "x = 1  # noqa: AK200, S603\n"
    noqa = parse_noqa(src)
    assert noqa[1] == {"AK200", "S603"}
    assert suppressed(noqa, "AK200", 1) is True
    # The foreign ruff code is inert for a2kit (no a2kit rule named S603).
    assert suppressed(noqa, "AK201", 1) is False


# --------------------------------------------------------------------------- #
# §2.2 — the a2kit code on a mixed line is ruff-grammar-shaped.
# --------------------------------------------------------------------------- #


def test_mixed_line_a2kit_code_is_ruff_parseable() -> None:
    # ruff's noqa grammar is `[A-Z]+[0-9]+`; a well-formed unknown code is
    # ignored by ruff, not a parse error. Pin that the a2kit token qualifies.
    assert RUFF_CODE.match("AK200")
    assert RUFF_CODE.match("AKR001")
    assert RUFF_CODE.match("RG002")
    # A dashed legacy code would NOT (this is the bug being fixed).
    assert not RUFF_CODE.match("A2K-LAYER")


# --------------------------------------------------------------------------- #
# §3.1 — the legacy alias table is complete, ruff-shaped, and injective.
# --------------------------------------------------------------------------- #


def test_legacy_alias_table_complete_and_injective() -> None:
    from a2kit.packages.lint.static import LEGACY_CODE_ALIASES

    # Every value is a new-shape code.
    bad = sorted(v for v in LEGACY_CODE_ALIASES.values() if not RUFF_CODE.match(v))
    assert bad == [], f"alias targets not ruff-shaped: {bad}"

    # Injective: no two legacy codes map to the same new code.
    values = list(LEGACY_CODE_ALIASES.values())
    assert len(values) == len(set(values)), "alias table is not injective"

    # Every known legacy dashed / A2K### / A2KR### / REGO- code is covered.
    for legacy in ("A2K-LAYER", "A2K014", "A2KR001", "REGO-NAME-COLLISION", "A2K-METADATA-PRIVATE"):
        assert legacy in LEGACY_CODE_ALIASES, f"{legacy} missing from alias table"


# --------------------------------------------------------------------------- #
# §3.2 — a legacy suppression still resolves to the renamed rule.
# --------------------------------------------------------------------------- #


def test_legacy_noqa_resolves_to_new_code() -> None:
    from a2kit.packages.lint.static import LEGACY_CODE_ALIASES, parse_noqa, suppressed

    new = LEGACY_CODE_ALIASES["A2K-LAYER"]
    src = "import x  # noqa: A2K-LAYER\n"
    noqa = parse_noqa(src)
    # The legacy code is normalized to the new code on parse.
    assert suppressed(noqa, new, 1) is True


# --------------------------------------------------------------------------- #
# §3.3 — emitted findings always carry the NEW code, never a legacy spelling.
# --------------------------------------------------------------------------- #


def test_anchored_renames_match_proposal() -> None:
    from a2kit.packages.lint.static import LEGACY_CODE_ALIASES

    # The proposal anchors these specific renames.
    assert LEGACY_CODE_ALIASES["A2K-LAYER"] == "AK200"
    assert LEGACY_CODE_ALIASES["A2K-METADATA-PRIVATE"] == "AK210"
    assert LEGACY_CODE_ALIASES["A2K014"] == "AK014"
    assert LEGACY_CODE_ALIASES["A2KR001"] == "AKR001"
    assert LEGACY_CODE_ALIASES["REGO-NAME-COLLISION"] == "RG002"


@pytest.mark.parametrize("legacy", ["A2K-LAYER", "A2K014", "REGO-BODY-DUP"])
def test_no_legacy_spelling_in_all_rules(legacy: str) -> None:
    from a2kit.packages.lint.runtime import ALL_CHECKS
    from a2kit.packages.lint.static import ALL_RULES

    assert legacy not in set(ALL_RULES) | set(ALL_CHECKS)
