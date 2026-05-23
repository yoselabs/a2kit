"""``--select EXPR`` runtime filter — front door (re-exports only).

Implementation lives in :mod:`a2kit.packages.select.dsl` per
A2K-PKG-INIT-IMPL (a package ``__init__.py`` is re-export plumbing,
not implementation).
"""

from __future__ import annotations

from a2kit.packages.select.dsl import (
    Category,
    Selector,
    SelectorError,
    compile_selector,
)

__all__ = ["Category", "Selector", "SelectorError", "compile_selector"]
