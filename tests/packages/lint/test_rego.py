"""Mirror tests for packages/lint/rego — `a2kit lint rego` subcommand wrapper.

End-to-end CLI behavior (exit codes, finding rendering) is covered in
tests/capabilities/rego_policy_layer/test_subcommand.py. This file
exercises the wrapper's helper functions directly.
"""

from __future__ import annotations

from a2kit.packages.lint.rego import RegoWrapperError, _to_lint_message


def test_to_lint_message_maps_all_fields():
    finding = {
        "rule": "REGO-BODY-DUP",
        "file": "src/foo.py",
        "line": 42,
        "col": 0,
        "message": "body matches src/bar.py:10",
    }
    msg = _to_lint_message(finding)
    assert msg.rule == "REGO-BODY-DUP"
    assert msg.filename == "src/foo.py"
    assert msg.line == 42
    assert msg.col == 0
    assert "body matches" in msg.message


def test_to_lint_message_tolerates_missing_fields():
    msg = _to_lint_message({})
    assert msg.rule == "REGO-UNKNOWN"
    assert msg.filename == "?"
    assert msg.line == 0
    assert msg.col == 0
    assert msg.message == ""


def test_to_lint_message_coerces_none_numeric_fields_to_zero():
    msg = _to_lint_message({"rule": "X", "file": "a.py", "line": None, "col": None, "message": ""})
    assert msg.line == 0
    assert msg.col == 0


def test_rego_wrapper_error_is_surfaceable():
    err = RegoWrapperError("oops")
    assert str(err) == "oops"
