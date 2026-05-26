"""Test seam — build :class:`Principal` instances without touching middleware.

Authors testing ``authorize=`` callables or tool bodies that resolve
``principal: Principal`` use :func:`make_principal` to construct a
synthetic identity, then either:

- override the DI provider on the App
  (``app.container().provide(Principal, lambda: p)``), or
- publish via the named bridge for tests without an App
  (``a2kit.packages.dispatch._principal_bridge.set_request_principal``).

The previous ``authenticated_as`` contextmanager was a thin wrapper
over the contextvar set/reset and was removed in
``consolidate-principal-bridge`` — the bridge writer API is the single
documented entry point.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

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


__all__ = ["make_principal"]
