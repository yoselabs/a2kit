"""Per-call side channel for ``ErrorEnvelopeStage`` rendered output.

The dispatch pipeline opens a per-call slot at the transport adapter
boundary; ``ErrorEnvelopeStage`` writes into it via
:func:`set_rendered_error`; transport render stages (MCP, CLI) read
via :func:`get_rendered_error`. ``AppError`` instances stay pure
domain values; rendering metadata lives outside the exception.

Replaces the prior pattern of mutating ``exc.rendered_prose`` and
``exc.rendered_envelope_dict`` (two ``# ty: ignore[unresolved-attribute]``
comments in ``envelope.py``) which silently coupled writer and readers
via untyped exception attributes.
"""

from __future__ import annotations

import contextlib
import contextvars
import weakref
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RenderedError:
    """Per-call rendered output for an in-flight ``AppError``."""

    prose: str
    envelope: dict[str, Any]  # noqa: A2K-NO-DICT-STR-ANY -- JSON error envelope is wire-format free-form by design


# Per-call slot. The transport adapter opens the slot before invoking
# the folded pipeline (so ``ErrorEnvelopeStage`` has a place to write)
# and closes it on exit. Within a single asyncio Context the dict
# object is shared by reference even across child-task spawns (FastMCP
# spawns child tasks for tool bodies), so writes from any task are
# visible to the reader.
_render_state: contextvars.ContextVar[dict[int, RenderedError] | None] = contextvars.ContextVar("_a2kit_render_state", default=None)


def open_render_state() -> contextvars.Token[dict[int, RenderedError] | None]:
    """Install a fresh per-call render-state slot. Return the reset token."""
    return _render_state.set({})


def close_render_state(token: contextvars.Token[dict[int, RenderedError] | None]) -> None:
    """Close the per-call slot by resetting the ContextVar binding."""
    _render_state.reset(token)


def set_rendered_error(exc: BaseException, rendered: RenderedError) -> None:
    """Stash ``rendered`` for ``exc`` in the active per-call slot.

    No-op when no slot is open (defensive — keeps non-dispatched callers,
    such as unit tests that exercise a stage in isolation, from raising).
    """
    state = _render_state.get()
    if state is None:
        return
    key = id(exc)
    state[key] = rendered
    # Auto-clean the entry when the exception is GC'd, in case the slot
    # outlives the exception lifetime (rare but defensive against leaks).
    # BaseException subclasses generally support weakref; suppress
    # TypeError for the rare subclass that disabled it.
    with contextlib.suppress(TypeError):
        weakref.finalize(exc, state.pop, key, None)


def get_rendered_error(exc: BaseException) -> RenderedError | None:
    """Look up rendered output for ``exc`` in the active per-call slot."""
    state = _render_state.get()
    if state is None:
        return None
    return state.get(id(exc))


__all__ = [
    "RenderedError",
    "close_render_state",
    "get_rendered_error",
    "open_render_state",
    "set_rendered_error",
]
