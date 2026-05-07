"""Select expression: façade that re-exports the parser + evaluator splits.

v0.4 split this 230-LOC module into `_select_parse.py` (~120 LOC) and
`_select_eval.py` (~80 LOC). This façade keeps the public re-exports
(`parse_select`, `SelectAtom`, `SelectExpr`, `sel`, `validate_atoms`,
`default_select_expr`) byte-equivalent for downstream code that imports from
`a2kit._select` directly.
"""

from __future__ import annotations

from a2kit._select_eval import sel, validate_atoms
from a2kit._select_parse import (
    SelectAtom,
    SelectExpr,
    default_select_expr,
    parse_select,
)

__all__ = [
    "SelectAtom",
    "SelectExpr",
    "default_select_expr",
    "parse_select",
    "sel",
    "validate_atoms",
]
