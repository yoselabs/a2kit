"""LDD level vocabulary and numeric ranks.

Lives in the ldd package (layer 0) so `a2kit.config` (layer 1, kernel)
can import from it without creating an upward edge. The threshold filter
in :mod:`a2kit.packages.ldd.emission` and the dispatch-site stamp in
:mod:`a2kit.packages.dispatch.stages` both read ``LDD_LEVEL_RANK``.

Rank spacing of 10 mirrors stdlib ``logging`` and leaves room for future
intermediate levels (e.g. ``notice=25``) without renumbering.
"""

from __future__ import annotations

from typing import Literal

LddLevel = Literal["trace", "debug", "info", "warning", "error"]

#: Numeric ranks for the LDD level vocabulary. Threshold comparison uses
#: these ranks (strict less-than → dropped).
LDD_LEVEL_RANK: dict[LddLevel, int] = {
    "trace": 10,
    "debug": 20,
    "info": 30,
    "warning": 40,
    "error": 50,
}

__all__ = ["LDD_LEVEL_RANK", "LddLevel"]
