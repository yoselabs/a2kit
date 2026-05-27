"""Canonical dispatch invocation helper — shared by every stage that
needs to call a possibly-async function and await the result if needed.

Resolves R1 from the 2026-05-27 structural audit (``_call`` duplicated
across ``dispatch/envelope.py`` and ``dispatch/stages.py``). Both routes
through this module.

Stdlib-only; no a2kit imports.
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable


async def _call(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Invoke ``fn`` and await the result if it is awaitable.

    The dispatch stages call user-provided tool functions that may be
    sync or async. This helper hides the await-or-not branching so the
    surrounding stage code stays linear.
    """
    result = fn(*args, **kwargs)
    if inspect.isawaitable(result):
        result = await result
    return result


__all__ = ["_call"]
