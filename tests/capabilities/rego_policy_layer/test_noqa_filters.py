"""1.4 — noqa ` -- <reason>` suppresses REGO-* findings; bare REGO-*
noqa is a hard error from extract_facts.py."""

from __future__ import annotations

from .conftest import extract, extract_returncode, opa_eval, write_py


def test_noqa_with_reason_suppresses_body_dup(tmpsrc):
    write_py(
        tmpsrc,
        "a.py",
        (
            "def _helper():  # noqa: RG001 -- intentional parallel impl, see ADR-NNNN\n"
            "    out = []\n"
            "    for x in range(3):\n"
            "        out.append(x)\n"
            "    return out\n"
        ),
    )
    write_py(tmpsrc, "b.py", ("def _helper():\n    res = []\n    for y in range(3):\n        res.append(y)\n    return res\n"))
    facts = extract([tmpsrc])
    suppressions = facts["suppressions"]
    assert any(s["rule_id"] == "RG001" and s["reason"] for s in suppressions)
    findings = opa_eval(facts, allowlist={"body_dup": [], "name_collision": []})
    body_dup = [f for f in findings if f["rule"] == "RG001"]
    assert not body_dup, f"noqa should have suppressed: {body_dup}"


def test_noqa_with_reason_suppresses_name_collision(tmpsrc):
    write_py(tmpsrc, "a.py", ("def _shared():  # noqa: RG002 -- valid reason\n    return 1\n"))
    write_py(tmpsrc, "b.py", "def _shared():\n    return 2\n")
    facts = extract([tmpsrc])
    findings = opa_eval(facts, allowlist={"body_dup": [], "name_collision": []})
    nc = [f for f in findings if f["rule"] == "RG002"]
    assert not nc, f"noqa should have suppressed: {nc}"


def test_rego_noqa_without_reason_is_hard_error(tmpsrc):
    write_py(tmpsrc, "a.py", ("def _helper():  # noqa: RG001\n    return 1\n"))
    code, stderr = extract_returncode([tmpsrc])
    assert code != 0, "REGO-* noqa without reason should fail extract"
    assert "RG001" in stderr
    assert "requires a reason" in stderr


def test_non_rego_noqa_without_reason_is_tolerated(tmpsrc):
    """A2K-* and other tool noqa retain existing tolerance."""
    write_py(tmpsrc, "a.py", ("def _helper():  # noqa: F401\n    return 1\n"))
    code, _stderr = extract_returncode([tmpsrc])
    assert code == 0, "non-REGO noqa without reason should be tolerated"
