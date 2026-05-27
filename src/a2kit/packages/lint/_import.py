"""Resolve a ``module:attr`` spec into the attribute — shared by ``a2kit lint runtime`` and scripts/find_similar."""

from __future__ import annotations

import importlib
from typing import Any


def import_target(spec: str) -> Any:
    """Import ``module:attr`` and return the attribute. Raises ``ValueError`` on bad spec."""
    if ":" not in spec:
        msg = f"--import requires module:attr, got {spec!r}"
        raise ValueError(msg)
    mod, attr = spec.split(":", 1)
    return getattr(importlib.import_module(mod), attr)


__all__ = ["import_target"]
