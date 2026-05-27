"""1.1 — extract_facts.py emits the documented JSON shape."""

from __future__ import annotations

from .conftest import extract, write_py


def test_extract_emits_documented_top_level_keys(tmpsrc):
    write_py(tmpsrc, "foo.py", "def hello():\n    return 1\n")
    facts = extract([tmpsrc])
    assert set(facts) == {"functions", "modules", "suppressions"}


def test_function_records_have_required_fields(tmpsrc):
    write_py(tmpsrc, "foo.py", "def hello():\n    return 1\n")
    facts = extract([tmpsrc])
    assert len(facts["functions"]) == 1
    fn = facts["functions"][0]
    required = {"file", "name", "line", "kind", "is_async", "is_private", "is_dunder", "body_stmt_count", "ast_hash_normalized"}
    assert required <= set(fn), f"missing: {required - set(fn)}"


def test_async_and_private_flags(tmpsrc):
    write_py(tmpsrc, "foo.py", "async def _private():\n    pass\n")
    facts = extract([tmpsrc])
    fn = facts["functions"][0]
    assert fn["is_async"] is True
    assert fn["is_private"] is True
    assert fn["is_dunder"] is False


def test_dunder_flag(tmpsrc):
    write_py(tmpsrc, "foo.py", "def __getattr__(name):\n    return None\n")
    facts = extract([tmpsrc])
    fn = facts["functions"][0]
    assert fn["is_dunder"] is True
    assert fn["is_private"] is False


def test_normalized_hash_equal_for_identical_shape_different_identifiers(tmpsrc):
    write_py(tmpsrc, "a.py", "def f(x):\n    return x + 1\n")
    write_py(tmpsrc, "b.py", "def g(y):\n    return y + 1\n")
    facts = extract([tmpsrc])
    hashes = {f["ast_hash_normalized"] for f in facts["functions"]}
    assert len(hashes) == 1, "identifier-only difference should normalize equal"


def test_normalized_hash_differs_for_different_operator(tmpsrc):
    write_py(tmpsrc, "a.py", "def f(x):\n    return x + 1\n")
    write_py(tmpsrc, "b.py", "def g(x):\n    return x * 2\n")
    facts = extract([tmpsrc])
    hashes = {f["ast_hash_normalized"] for f in facts["functions"]}
    assert len(hashes) == 2, "different operator should hash differently"


def test_docstring_does_not_affect_hash(tmpsrc):
    write_py(tmpsrc, "a.py", "def f(x):\n    return x + 1\n")
    write_py(tmpsrc, "b.py", '''def f(x):\n    """docstring"""\n    return x + 1\n''')
    facts = extract([tmpsrc])
    hashes = {f["ast_hash_normalized"] for f in facts["functions"]}
    assert len(hashes) == 1, "docstring presence should not affect hash"


def test_body_stmt_count_is_recursive(tmpsrc):
    """A single try/except wrapping 3 inner stmts counts as 4, not 1."""
    write_py(
        tmpsrc,
        "foo.py",
        ("def f():\n    try:\n        a = 1\n        b = 2\n        return a + b\n    except Exception:\n        return 0\n"),
    )
    facts = extract([tmpsrc])
    fn = facts["functions"][0]
    assert fn["body_stmt_count"] >= 4, f"got {fn['body_stmt_count']}"


def test_deterministic_output(tmpsrc):
    write_py(tmpsrc, "foo.py", "def f():\n    return 1\n")
    a = extract([tmpsrc])
    b = extract([tmpsrc])
    import json

    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
