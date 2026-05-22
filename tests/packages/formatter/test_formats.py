"""Tests for `a2kit.packages.formatter.formats` — the wire-format vocabulary."""

from __future__ import annotations

from typing import get_args


def test_leaf_module_exposes_the_aliases() -> None:
    from a2kit.packages.formatter import formats

    assert set(get_args(formats.FormatHint)) == {"auto", "json", "tsv", "page-tsv"}
    assert set(get_args(formats.FormatName)) == {"json", "tsv"}


def test_package_reexports_the_leaf_aliases() -> None:
    """The package re-exports the leaf aliases unchanged (design D3)."""
    from a2kit.packages import formatter
    from a2kit.packages.formatter import formats

    assert formatter.FormatHint is formats.FormatHint
    assert formatter.FormatName is formats.FormatName
