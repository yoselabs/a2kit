"""Mirror tests for packages/connections/_validation — canonical key validation."""

from __future__ import annotations

import pytest

from a2kit.packages.connections._validation import validate_key, validate_key_part
from a2kit.packages.connections.exceptions import InvalidConnectionKey


def test_validate_key_part_passes_valid():
    assert validate_key_part("foo") == "foo"
    assert validate_key_part("a-b_c.d") == "a-b_c.d"
    assert validate_key_part("Aa0") == "Aa0"


def test_validate_key_part_rejects_empty():
    with pytest.raises(InvalidConnectionKey):
        validate_key_part("")


def test_validate_key_part_rejects_leading_special():
    with pytest.raises(InvalidConnectionKey):
        validate_key_part("-foo")
    with pytest.raises(InvalidConnectionKey):
        validate_key_part(".foo")


def test_validate_key_passes_valid_tuple():
    assert validate_key(("foo", "bar")) == ("foo", "bar")
    assert validate_key(("single",)) == ("single",)


def test_validate_key_rejects_empty_tuple():
    with pytest.raises(InvalidConnectionKey):
        validate_key(())


def test_validate_key_rejects_bad_segment():
    with pytest.raises(InvalidConnectionKey):
        validate_key(("foo", " bad space"))
