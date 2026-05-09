"""Thin wrapper around the ``toon_format`` library.

Why wrap instead of re-export?

- Keeps the import boundary explicit: the rest of a2kit talks to
  ``encode_toon``; only this module knows the third-party name.
- Lets us swap encoders (e.g. a vendored fallback) without touching callers.
- Pre-release pin gotcha: ``toon-format==0.1.0`` ships a ``NotImplementedError``
  stub. Production builds must pin ``==0.9.0bN`` or later. We assert in tests
  that we're hitting the real encoder.

Do NOT re-export ``toon_format`` symbols from the package ``__init__``.
"""

from __future__ import annotations

from typing import Any

import toon_format


def encode_toon(value: Any) -> str:
    """Encode ``value`` using the real ``toon_format`` encoder.

    Byte-identical to ``toon_format.encode(value)`` — this is a one-line
    indirection so the rest of the codebase has a stable import name.
    """
    return toon_format.encode(value)


__all__ = ["encode_toon"]
