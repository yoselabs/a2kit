"""Lifespan composition primitive for the ``lifespan=`` App argument.

``compose(*lifespans)`` returns a single async context manager that runs
each supplied lifespan in declared order on entry and unwinds them in
reverse (LIFO) on exit via :class:`contextlib.AsyncExitStack`. Each
shutdown leg is wrapped so an exception there is logged via
``logging.getLogger("a2kit.lifecycle")`` and the remaining legs still
unwind.

The shape of each lifespan in ``*lifespans`` is the canonical a2kit
shape: an ``@asynccontextmanager async def lifespan(app)`` callable.
``compose`` returns a callable with the same shape: ``async def
composed(app)`` returning an ``AsyncContextManager``. Pass the result to
``a2kit.App(..., lifespan=composed)``.

Example::

    @asynccontextmanager
    async def app_lifespan(app):
        ...
        yield

    composed = a2kit.lifespan.compose(app_lifespan, router_a.lifespan, router_b.lifespan)
    app = a2kit.App("x", lifespan=composed)
"""

from __future__ import annotations

import logging
from contextlib import AsyncExitStack, asynccontextmanager
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable

_LOG = logging.getLogger("a2kit.lifecycle")


def compose(
    *lifespans: Callable[[Any], Any],
) -> Callable[[Any], Any]:
    """Compose ``*lifespans`` into a single ``lifespan(app)`` callable.

    Startup runs in declared order; shutdown runs in reverse order
    (LIFO unwind via :class:`contextlib.AsyncExitStack`). Each shutdown
    leg is wrapped so an exception is logged under
    ``a2kit.lifecycle`` at ``ERROR`` with traceback and unwinding
    continues. If any startup leg raises mid-stack, already-entered legs
    are unwound and the exception propagates to the caller (standard
    ``AsyncExitStack`` semantics).
    """

    @asynccontextmanager
    async def _composed(app: Any) -> AsyncIterator[None]:
        async with AsyncExitStack() as stack:
            for ls in lifespans:
                shielded = _ShieldShutdown(ls(app), ls)
                await stack.enter_async_context(shielded)
            yield

    return _composed


class _ShieldShutdown:
    """Async-context-manager wrapper that swallows shutdown exceptions.

    Startup (``__aenter__``) is transparent: any exception raised by the
    wrapped CM's enter propagates as-is so :class:`AsyncExitStack` can
    unwind already-entered legs.

    Shutdown (``__aexit__``) is shielded: if the wrapped CM's exit
    raises, the exception is logged under ``a2kit.lifecycle`` at ERROR
    with traceback and treated as "exit succeeded" (returns False) so
    sibling legs still unwind. If the body raised and the wrapped CM's
    exit raises a NEW exception trying to handle it, the original body
    exception is preserved (the new exit error is logged).
    """

    def __init__(self, cm: Any, label: Any) -> None:
        self._cm = cm
        self._label = label

    async def __aenter__(self) -> Any:
        return await self._cm.__aenter__()

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        try:
            result = await self._cm.__aexit__(exc_type, exc, tb)
        except Exception:  # noqa: BLE001
            _LOG.exception(
                "lifespan %r raised on shutdown; continuing",
                _label_repr(self._label),
            )
            # Original body exception (if any) is preserved by returning
            # False; sibling legs continue to unwind.
            return False
        return bool(result)


def _label_repr(label: Any) -> str:
    return getattr(label, "__qualname__", getattr(label, "__name__", repr(label)))


__all__ = ["compose"]
