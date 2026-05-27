"""Mirror tests for packages/lint/_distance — Levenshtein helper."""

from __future__ import annotations

from a2kit.packages.lint._distance import edit_distance


def test_equal_strings_zero():
    assert edit_distance("foo", "foo") == 0


def test_single_substitution():
    assert edit_distance("cat", "bat") == 1


def test_single_insertion():
    assert edit_distance("cat", "cats") == 1


def test_short_circuit_long_diff():
    # length diff > 2 → returns 3 (sentinel "far enough")
    assert edit_distance("a", "abcd") == 3


def test_swap_costs_two():
    assert edit_distance("ab", "ba") == 2
