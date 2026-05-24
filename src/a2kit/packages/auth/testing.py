"""Test seam — bind a :class:`Principal` without spinning up middleware.

Authors testing ``authorize=`` callables or tool bodies that resolve
``principal: Principal`` use ``authenticated_as(...)`` to bind the
contextvar for the duration of a block. The MCP / HTTP middlewares
do the same thing in production; this helper isolates the bind without
the substrate machinery.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

    from a2kit.packages.context import Principal


def make_principal(
    *,
    subject: str,
    scopes: Iterable[str] = (),
    claims: dict | None = None,
    issued_by: str = "test",
) -> Principal:
    """Construct a :class:`Principal` for unit-test use.

    Defaults match the most-tested shape: a known subject, a scope
    frozenset, no claims, ``issued_by="test"`` so trace output makes
    the synthetic origin obvious.
    """
    from a2kit.packages.context import Principal

    return Principal(
        subject=subject,
        scopes=frozenset(scopes),
        claims=claims or {},
        issued_by=issued_by,
        raw_token=None,
    )


@contextlib.contextmanager
def authenticated_as(principal: Principal) -> Iterator[None]:
    """Bind ``principal`` on ``_a2kit_request_principal`` for the block.

    Resets the contextvar on exit, whether the block raised or not.
    Equivalent to what the production middlewares do per request, but
    callable directly from a test without an ASGI scope.
    """
    from a2kit.packages.context import _a2kit_request_principal

    token = _a2kit_request_principal.set(principal)
    try:
        yield
    finally:
        _a2kit_request_principal.reset(token)


__all__ = ["authenticated_as", "make_principal"]
