"""Lifecycle helpers extracted from ``a2kit.app`` for the
``consolidate-lifecycle-on-async-cm-protocol`` change.

Pure functions (no App state). Lives at the top of the package so it
imports cleanly from ``a2kit.app`` without circulars.
"""

from __future__ import annotations

import inspect
import typing
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable


def resolve_singleton_args(arg1: Any, arg2: Any) -> tuple[type, Callable[..., Any]]:
    """Resolve the ``(type, factory)`` pair from ``app.provide`` call args.

    Three shapes (per ``consolidate-lifecycle-on-async-cm-protocol``):

    - ``singleton(Class)`` → ``(Class, Class)``
    - ``singleton(factory)`` → ``(factory_return_type, factory)``
    - ``singleton(BaseClass, factory)`` → ``(BaseClass, factory)``

    Unannotated callables raise ``TypeError`` with an action-oriented
    message naming both fixes.
    """
    if arg2 is None:
        if inspect.isclass(arg1):
            return arg1, arg1
        if callable(arg1):
            return_type = return_type_of(arg1)
            if return_type is None:
                raise TypeError(
                    f"app.provide({arg1!r}) requires a return annotation. "
                    "Either annotate the factory ('-> T') or pass the type "
                    "explicitly: app.provide(T, factory)."
                )
            return return_type, arg1
        msg = f"app.provide({arg1!r}): expected a class or callable factory"
        raise TypeError(msg)
    if not inspect.isclass(arg1):
        msg = f"app.provide({arg1!r}, {arg2!r}): first positional must be a type when a factory is supplied"
        raise TypeError(msg)
    return arg1, arg2


def return_type_of(fn: Callable[..., Any]) -> type | None:
    """Read the return-type annotation off ``fn`` as a runtime type.

    Returns ``None`` when the function carries no return annotation or
    the annotation cannot be resolved to a runtime class. Generic
    aliases (``list[int]``, ``Optional[Foo]``) are not resolved here —
    the caller decides whether to widen the contract.
    """
    try:
        hints = typing.get_type_hints(fn)
    except Exception:  # noqa: BLE001 -- annotation may reference unresolved names
        hints = {}
    rtype = hints.get("return")
    if rtype is None:
        try:
            rtype = inspect.signature(fn).return_annotation
        except (TypeError, ValueError):
            rtype = inspect.Signature.empty
    if rtype is inspect.Signature.empty or rtype is None:
        return None
    if inspect.isclass(rtype):
        return rtype
    return None


async def register_instance_cleanup(stack: Any, instance: Any) -> None:
    """Probe ``instance`` for cleanup protocol and register on ``stack``.

    Order (per ``app-singletons`` delta):

    1. ``__aexit__`` paired with ``__aenter__`` — enter eagerly via
       ``stack.enter_async_context(instance)`` so ``__aexit__`` runs
       on stack unwind.
    2. ``aclose()`` — scheduled via ``stack.push_async_callback``.
    3. ``close()`` — scheduled as a sync or async callback depending
       on whether the call returns a coroutine.
    4. None — no teardown registered (intentional; some instances
       genuinely have no cleanup).
    """
    if hasattr(instance, "__aexit__") and hasattr(instance, "__aenter__"):
        await stack.enter_async_context(instance)
        return
    if hasattr(instance, "aclose"):
        stack.push_async_callback(instance.aclose)
        return
    if hasattr(instance, "close"):

        async def _wrapped_close() -> None:
            result = instance.close()
            if inspect.isawaitable(result):
                await result

        stack.push_async_callback(_wrapped_close)
