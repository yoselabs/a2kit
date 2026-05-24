"""Per-request DI scope contextvar — bridge seam for FastAPI `Depends`.

The HTTP middleware in `packages/http/build.py` opens a child container
per request and sets this contextvar to it. The resolvers produced by
`Container.expose_as_fastapi_depends(T)` read the contextvar and call
`await scope.get(T)` so FastAPI's own dependency graph can resolve
a2kit container-known types.

Kept separate from `packages/dispatch/substrate.py`'s `_a2kit_scope`
sentinel to avoid disturbing the wrapper-internal contract while the
bridge lands. Substrate-wrapper unification is the seam owned by
`unify-signature-installers`.
"""

from __future__ import annotations

import contextvars
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from a2kit.packages.di.container import Container

_a2kit_request_scope: contextvars.ContextVar[Container | None] = contextvars.ContextVar(
    "_a2kit_request_scope",
    default=None,
)


__all__ = ["_a2kit_request_scope"]
