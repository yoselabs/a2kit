"""Mirror tests for packages/lint/_import — module:attr resolver."""

from __future__ import annotations

import pytest

from a2kit.packages.lint._import import import_target


def test_imports_attribute():
    fn = import_target("a2kit.packages.lint._distance:edit_distance")
    assert fn("a", "a") == 0


def test_rejects_missing_colon():
    with pytest.raises(ValueError, match="module:attr"):
        import_target("no_colon_here")


def test_raises_on_missing_attr():
    with pytest.raises(AttributeError):
        import_target("a2kit.packages.lint._distance:does_not_exist")
