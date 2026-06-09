"""1.3 — name_collision.rego catches cross-file private-helper name reuse.

R1 (the historical motivation, `_call` x 2) is closed in the same change
that lands this policy via the canonical `packages/dispatch/_invoke.py`.
Synthetic fixtures exercise the policy below.
"""

from __future__ import annotations

from .conftest import extract, opa_eval, write_py


def test_name_collision_fires_for_private_name_in_two_files(tmpsrc):
    write_py(tmpsrc, "a.py", "def _helper():\n    return 1\n")
    write_py(tmpsrc, "b.py", "def _helper():\n    return 2\n")
    facts = extract([tmpsrc])
    findings = opa_eval(facts, allowlist={"body_dup": [], "name_collision": []})
    nc = [f for f in findings if f["rule"] == "RG002"]
    assert nc, "expected RG002 to fire"
    assert "_helper" in nc[0]["message"]


def test_name_collision_does_not_fire_for_dunder(tmpsrc):
    """__getattr__ etc. are legitimate per-module conventions."""
    write_py(tmpsrc, "a.py", "def __getattr__(name):\n    return None\n")
    write_py(tmpsrc, "b.py", "def __getattr__(name):\n    return None\n")
    facts = extract([tmpsrc])
    findings = opa_eval(facts, allowlist={"body_dup": [], "name_collision": []})
    assert not [f for f in findings if f["rule"] == "RG002"]


def test_name_collision_does_not_fire_for_public_names(tmpsrc):
    """Public-name collisions (foo, not _foo) are out of scope."""
    write_py(tmpsrc, "a.py", "def helper():\n    return 1\n")
    write_py(tmpsrc, "b.py", "def helper():\n    return 2\n")
    facts = extract([tmpsrc])
    findings = opa_eval(facts, allowlist={"body_dup": [], "name_collision": []})
    assert not [f for f in findings if f["rule"] == "RG002"]


def test_name_collision_allowlist_drops_name(tmpsrc):
    write_py(tmpsrc, "a.py", "def _intentional():\n    return 1\n")
    write_py(tmpsrc, "b.py", "def _intentional():\n    return 2\n")
    facts = extract([tmpsrc])
    findings = opa_eval(
        facts,
        allowlist={
            "body_dup": [],
            "name_collision": [{"names": ["_intentional"], "reason": "test"}],
        },
    )
    assert not [f for f in findings if f["rule"] == "RG002"]


def test_name_collision_does_not_fire_within_same_file(tmpsrc):
    write_py(tmpsrc, "single.py", ("def _foo():\n    return 1\nclass C:\n    def _foo(self):\n        return 2\n"))
    facts = extract([tmpsrc])
    findings = opa_eval(facts, allowlist={"body_dup": [], "name_collision": []})
    assert not [f for f in findings if f["rule"] == "RG002"]
