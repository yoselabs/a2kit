"""1.2 — body_dup.rego catches cross-file body duplication.

R6 (the historical motivation) is closed in the same change that lands
this policy via the foundational `a2kit._ldd_wire` module — so the
real codebase no longer fires the finding. Instead, these tests use
synthetic fixtures to exercise the policy behavior directly.
"""

from __future__ import annotations

from .conftest import extract, opa_eval, write_py


def _make_dup_fixture(tmpsrc, name: str):
    """Two files with the same 4-statement body, identifier-renamed."""
    body_a = f"def {name}(items):\n    out = []\n    for item in items:\n        out.append(item)\n    return out\n"
    body_b = f"def {name}(things):\n    result = []\n    for thing in things:\n        result.append(thing)\n    return result\n"
    write_py(tmpsrc, "a.py", body_a)
    write_py(tmpsrc, "b.py", body_b)


def test_body_dup_fires_for_cross_file_match(tmpsrc):
    _make_dup_fixture(tmpsrc, "process_items")
    facts = extract([tmpsrc])
    findings = opa_eval(facts, allowlist={"body_dup": [], "name_collision": []})
    body_dup_findings = [f for f in findings if f["rule"] == "REGO-BODY-DUP"]
    assert body_dup_findings, "expected REGO-BODY-DUP to fire"
    msg = body_dup_findings[0]["message"]
    assert "process_items" in msg or "b.py" in msg


def test_body_dup_respects_body_stmt_count_floor(tmpsrc):
    """Two-statement bodies should NOT fire (floor is 3)."""
    write_py(tmpsrc, "a.py", "def f():\n    x = 1\n    return x\n")
    write_py(tmpsrc, "b.py", "def g():\n    y = 1\n    return y\n")
    facts = extract([tmpsrc])
    findings = opa_eval(facts, allowlist={"body_dup": [], "name_collision": []})
    assert not [f for f in findings if f["rule"] == "REGO-BODY-DUP"], "should not fire on bodies below stmt-count floor"


def test_body_dup_allowlist_drops_matched_pair(tmpsrc):
    _make_dup_fixture(tmpsrc, "intentional_dup")
    facts = extract([tmpsrc])
    findings = opa_eval(
        facts,
        allowlist={
            "body_dup": [{"names": ["intentional_dup"], "reason": "test"}],
            "name_collision": [],
        },
    )
    assert not [f for f in findings if f["rule"] == "REGO-BODY-DUP"], "allowlisted pair should be filtered"


def test_body_dup_does_not_fire_within_same_file(tmpsrc):
    """Two identical functions in the SAME file should not fire body_dup
    (intra-file repetition is out of scope for this rule)."""
    src = "def a():\n    x = 1\n    y = 2\n    return x + y\ndef b():\n    p = 1\n    q = 2\n    return p + q\n"
    write_py(tmpsrc, "single.py", src)
    facts = extract([tmpsrc])
    findings = opa_eval(facts, allowlist={"body_dup": [], "name_collision": []})
    assert not [f for f in findings if f["rule"] == "REGO-BODY-DUP"]
