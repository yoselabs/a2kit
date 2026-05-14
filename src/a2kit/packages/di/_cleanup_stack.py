"""Custom per-scope LIFO cleanup stack.

Replaces ``contextlib.AsyncExitStack`` because that primitive has known
unwind hazards under exception during ``__aexit__`` of nested CMs:

- cpython #137517: background-task exception during AsyncExitStack close
  swallows / re-raises confusingly.
- MCP SDK #1213: partial-entry-on-startup-failure leaks half-entered
  resources because the stack is built before any entry succeeds.
- trio #1243: AsyncExitStack-equivalent in trio reorders cleanup under
  cancellation in a way that loses the original exception.

This stack records each successfully entered resource as
``(type, aexit_callable)``. On ``aclose``:

1. Pops in LIFO order.
2. For each entry, calls the aexit callable inside an isolated
   ``try/except Exception`` — a misbehaving resource's exit error is
   logged to ``a2kit.di.cleanup`` and does NOT abort sibling unwinds.
3. If a body exception is present (passed in via :meth:`aclose`), it
   wins; cleanup errors only surface if no body exception was present.

Partial-entry safety: callers MUST only :meth:`record` after the
resource is fully entered (``__aenter__`` returned, or the generator
advanced past its ``yield``). An entry that raises mid-init is never
recorded, so the unwind does not call its ``__aexit__``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


_log = logging.getLogger("a2kit.di.cleanup")


@dataclass(slots=True)
class CleanupStack:
    """LIFO stack of ``(type, aexit_callable)`` entries.

    One stack per scope (app-scope = root container's stack; per-call
    scope = child container's stack).
    """

    _entries: list[tuple[type, Callable[..., Awaitable[None]]]] = field(default_factory=list)
    _closed: bool = False

    def record(self, type_: type, aexit: Callable[..., Awaitable[None]]) -> None:
        """Register a cleanup callable for ``type_``.

        ``aexit`` is called as ``aexit(exc_type, exc, tb)`` at unwind so
        the resource sees the surrounding exception context (matching
        Python ``async with`` semantics). Call AFTER successful entry —
        partial-entry safety depends on the caller's discipline here.
        """
        if self._closed:
            msg = f"CleanupStack already closed; cannot record entry for {type_!r}"
            raise RuntimeError(msg)
        self._entries.append((type_, aexit))

    async def aclose(
        self,
        exc_type: type[BaseException] | None = None,
        exc: BaseException | None = None,
        tb: object | None = None,
    ) -> None:
        """Unwind in LIFO order with per-entry exception isolation.

        Forwards ``(exc_type, exc, tb)`` to each recorded ``__aexit__`` so
        per-call resources can react to the propagating exception (e.g.
        rollback on error, commit on clean exit). Each entry's failure is
        logged at ERROR level on ``a2kit.di.cleanup`` and the unwind
        continues; sibling resources still get their cleanup.
        """
        if self._closed:
            return
        self._closed = True
        # LIFO: pop from the end.
        while self._entries:
            type_, aexit = self._entries.pop()
            try:
                await aexit(exc_type, exc, tb)
            except Exception as cleanup_err:
                # Per-resource isolation. Sibling cleanups must still run.
                # Logged at WARN with the exception's str so the underlying
                # message (e.g. "B failed to exit") is visible in caplog
                # records, plus exc_info for the full traceback.
                _log.warning(
                    "cleanup error in __aexit__ for %r: %s",
                    type_,
                    cleanup_err,
                    exc_info=True,
                )
