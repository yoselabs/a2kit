"""1.5 — allowlist with reason filters findings; missing/empty reason fails."""

from __future__ import annotations

from .conftest import extract, opa_eval, write_py


def _dup_fixture(tmpsrc):
    write_py(tmpsrc, "a.py", "def _x():\n    return 1\n")
    write_py(tmpsrc, "b.py", "def _x():\n    return 2\n")


def test_allowlist_with_reason_drops_finding(tmpsrc):
    _dup_fixture(tmpsrc)
    facts = extract([tmpsrc])
    findings = opa_eval(
        facts,
        allowlist={
            "body_dup": [],
            "name_collision": [{"names": ["_x"], "reason": "intentional"}],
        },
    )
    nc = [f for f in findings if f["rule"] == "RG002"]
    assert not nc


def test_allowlist_missing_reason_field_raises_rego_allowlist(tmpsrc):
    _dup_fixture(tmpsrc)
    facts = extract([tmpsrc])
    findings = opa_eval(
        facts,
        allowlist={
            "body_dup": [],
            "name_collision": [{"names": ["_x"]}],  # no reason field
        },
    )
    rego_allowlist_findings = [f for f in findings if f["rule"] == "RG003"]
    assert rego_allowlist_findings, "missing reason should produce RG003 finding"


def test_allowlist_empty_reason_raises_rego_allowlist(tmpsrc):
    _dup_fixture(tmpsrc)
    facts = extract([tmpsrc])
    findings = opa_eval(
        facts,
        allowlist={
            "body_dup": [],
            "name_collision": [{"names": ["_x"], "reason": ""}],
        },
    )
    rego_allowlist_findings = [f for f in findings if f["rule"] == "RG003"]
    assert rego_allowlist_findings, "empty reason should produce RG003 finding"
