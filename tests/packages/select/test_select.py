"""Tests for `a2kit.packages.select` — cel-python compile / evaluate / validate."""

from __future__ import annotations

import pytest

from a2kit.exceptions import InvalidFilterExpression
from a2kit.packages.select import (
    UnknownAtomError,
    compile,
    evaluate,
    validate_atoms,
)

# Round-1 T1.1 legacy → CEL translation table. Each row pairs the legacy form
# (kept here for documentation only — never executed) with the CEL form we
# now require, plus an atoms dict and the expected boolean.
LEGACY_TO_CEL = [
    # legacy                                    cel                                          atoms                                                                       expected
    ("default and not write", "default && !write", {"default": True, "write": False}, True),
    (
        "default and not write and surface.mcp",
        "default && !write && surface.mcp",
        {"default": True, "write": False, "surface": {"mcp": True, "cli": False}},
        True,
    ),
    ("surface.cli", "surface.cli", {"surface": {"mcp": False, "cli": True}}, True),
    ("surface.mcp", "surface.mcp", {"surface": {"mcp": True, "cli": False}}, True),
    ("cap:write", "cap.write", {"cap": {"write": True}}, True),
    ("tool:foo", "tool.foo", {"tool": {"foo": True, "bar": False}}, True),
    ("default", "default", {"default": True}, True),
    ("not default", "!default", {"default": False}, True),
]


@pytest.mark.parametrize(("legacy", "cel", "atoms", "expected"), LEGACY_TO_CEL)
def test_legacy_translation_table(legacy: str, cel: str, atoms: dict, expected: bool) -> None:
    """Each legacy form has a CEL counterpart that compiles + evaluates correctly."""
    program = compile(cel)
    assert evaluate(program, atoms) is expected


def test_compile_returns_program_with_source() -> None:
    program = compile("default && !write")
    assert program.expr == "default && !write"


def test_compile_syntax_error_raises_invalid_filter() -> None:
    with pytest.raises(InvalidFilterExpression) as ei:
        compile("default &&")
    assert "CEL parse error" in str(ei.value)


def test_compile_empty_expression_rejected() -> None:
    with pytest.raises(InvalidFilterExpression):
        compile("")
    with pytest.raises(InvalidFilterExpression):
        compile("   ")


def test_evaluate_returns_python_bool() -> None:
    program = compile("default")
    out = evaluate(program, {"default": True})
    assert out is True
    assert isinstance(out, bool)


def test_evaluate_non_bool_result_raises() -> None:
    program = compile("1 + 2")
    with pytest.raises(InvalidFilterExpression) as ei:
        evaluate(program, {})
    assert "must evaluate to bool" in str(ei.value)


def test_evaluate_unknown_atom_raises_unknown_atom_error() -> None:
    program = compile("default && !writ")
    with pytest.raises(UnknownAtomError) as ei:
        evaluate(program, {"default": True, "write": False})
    assert ei.value.atom == "writ"
    # subclass of InvalidFilterExpression for the catch-all
    assert isinstance(ei.value, InvalidFilterExpression)


def test_evaluate_unknown_atom_includes_did_you_mean() -> None:
    program = compile("writ")
    with pytest.raises(UnknownAtomError) as ei:
        evaluate(program, {"write": True, "default": True})
    msg = str(ei.value)
    assert "did you mean" in msg
    assert "'write'" in msg


def test_validate_atoms_passes_for_known() -> None:
    validate_atoms("default && !write", {"default", "write"})


def test_validate_atoms_handles_dotted_access() -> None:
    validate_atoms(
        "tool.foo && cap.write && surface.mcp",
        {"tool.foo", "cap.write", "surface.mcp"},
    )


def test_validate_atoms_strict_typo() -> None:
    with pytest.raises(UnknownAtomError) as ei:
        validate_atoms("default && writ", {"default", "write"})
    assert ei.value.atom == "writ"


def test_validate_atoms_strict_dotted_typo() -> None:
    with pytest.raises(UnknownAtomError) as ei:
        validate_atoms("tool.fo", {"tool.foo", "tool.bar"})
    assert ei.value.atom == "tool.fo"


def test_validate_atoms_did_you_mean_in_message() -> None:
    with pytest.raises(UnknownAtomError) as ei:
        validate_atoms("writ", {"write", "default"})
    assert "did you mean" in str(ei.value)


def test_legacy_keyword_syntax_rejected() -> None:
    """Legacy `and`/`or`/`not` keywords are NOT valid CEL — must raise."""
    with pytest.raises(InvalidFilterExpression):
        compile("default and not write")


def test_legacy_colon_atom_syntax_rejected() -> None:
    """Legacy `cap:write` colon atoms are NOT valid CEL."""
    with pytest.raises(InvalidFilterExpression):
        compile("cap:write")


def test_unknown_atom_error_carries_known_set() -> None:
    err = UnknownAtomError("xyz", "xyz", {"a", "b"})
    assert err.atom == "xyz"
    assert err.known == {"a", "b"}
    assert err.expr == "xyz"


def test_evaluate_with_complex_nested_atoms() -> None:
    program = compile("(tool.alpha || tool.beta) && !cap.destructive")
    atoms = {
        "tool": {"alpha": False, "beta": True},
        "cap": {"destructive": False},
    }
    assert evaluate(program, atoms) is True
