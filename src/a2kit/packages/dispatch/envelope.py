"""Error envelope rendering: prose formatter + kind label registry + dispatch stage.

The prose formatter and kind label registry are pure functions reused
by every surface (MCP, HTTP, CLI). ``ErrorEnvelopeStage`` is the
terminal stage of the dispatch pipeline (after ``EnricherStage``,
before surface rendering): on any escaping ``AppError`` it pre-computes
``rendered_prose`` and ``rendered_envelope_dict`` attributes on the
exception so surface adapters can read them without re-running the
formatter per transport.
"""

from __future__ import annotations

import functools
import inspect
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable


_CORE_KIND_LABELS: dict[str, str] = {
    "input": "Input error",
    "auth": "Authentication required",
    "policy": "Not allowed",
    "infra": "Service unavailable",
    "bug": "Internal error",
}


def kind_label(kind: str) -> str:
    """Return the human-readable label for ``kind``.

    Falls back to capitalized kind name for unregistered extension kinds.
    """
    label = _CORE_KIND_LABELS.get(kind)
    if label is not None:
        return label
    from a2effect.errors import _KIND_EXTENSIONS

    ext = _KIND_EXTENSIONS.get(kind)
    if ext is not None:
        return _CORE_KIND_LABELS[ext.base]
    return kind.capitalize()


def format_error_prose(exc: Any) -> str:
    """Render an ``AppError`` to the fixed prose form.

    Format::

        {KindLabel} ({Type}): {message}

        Hint: {hint}

    The ``Hint:`` block is omitted entirely when ``hint`` is None.
    """
    cls = type(exc)
    label = cls.kind_label if cls.kind_label is not None else kind_label(cls.kind)
    type_name = cls.__name__
    message = str(exc)
    head = f"{label} ({type_name}): {message}"
    if exc.hint:
        return f"{head}\n\nHint: {exc.hint}"
    return head


async def _call(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    result = fn(*args, **kwargs)
    if inspect.isawaitable(result):
        result = await result
    return result


class ErrorEnvelopeStage:
    """Pre-compute prose + envelope dict on any escaping ``AppError``.

    Terminal stage: surface adapters (MCP/HTTP/CLI) then read
    ``rendered_prose`` and ``rendered_envelope_dict`` off the exception
    without re-running the formatter per transport. Non-``AppError``
    exceptions propagate untouched (the enricher stage's quarantine
    runs before this stage).
    """

    name = "error-envelope"

    def wrap(self, fn: Callable[..., Any], spec: Any) -> Callable[..., Any]:  # noqa: ARG002
        from a2effect import AppError

        @functools.wraps(fn)
        async def _wrapped(*args: Any, **kwargs: Any) -> Any:
            try:
                return await _call(fn, *args, **kwargs)
            except AppError as exc:
                # Stash transport-neutral render artifacts on the exception
                # for surface adapters (MCP / CLI) to read via getattr.
                # `AppError` is owned by a2effect and intentionally does not
                # declare these — a2kit's dispatch contract attaches them.
                exc.rendered_prose = format_error_prose(exc)  # ty: ignore[unresolved-attribute]
                exc.rendered_envelope_dict = exc.to_envelope_dict()  # ty: ignore[unresolved-attribute]
                raise

        return _wrapped


__all__ = ["ErrorEnvelopeStage", "format_error_prose", "kind_label"]
