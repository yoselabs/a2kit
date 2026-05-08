"""Dependency-injection types for v0.15.

a2kit's DI is intentionally tiny — one marker class plus a resolver. The
FastAPI/FastMCP idiom is the only DI path:

    from typing import Annotated
    from a2kit.di import Depends

    async def get_conn(*, connection: str) -> TrackerConn: ...

    @MyRouter.read()
    async def list_tasks(*, conn: Annotated[TrackerConn, Depends(get_conn)]) -> list[Task]:
        ...

The kit walks `Annotated[T, Depends(factory)]` markers on each tool's
kwonly params, resolves each factory (chaining transitively), and injects
the resolved values at call time. Tests override factories via
`app.dependency_overrides[get_conn] = fake_get_conn`.

Pre-v0.15 users had `Provider` / `Plugin` / `PluginBase` / `Binding` /
`ToolPlan` Protocols here; v0.15 deletes the lot in favour of the single
Annotated/Depends idiom.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Any, get_args, get_origin, get_type_hints

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


@dataclass(frozen=True, slots=True)
class Depends:
    """FastAPI-idiom DI marker. Use inside `Annotated[T, Depends(factory)]`
    on a tool's kwonly param; the kit calls `factory()` at tool-call time and
    injects the result.

    `factory` may be sync or async, and may itself declare `Annotated[..., Depends(...)]`
    kwonly params — the resolver walks the chain and caches per call.
    """

    dependency: Callable[..., Any] | Callable[..., Awaitable[Any]]
    use_cache: bool = True


class DependsCycleError(Exception):
    """Annotated-Depends factory graph contains a cycle. Raised at call time
    (cycle is data-dependent on the factory annotations)."""

    def __init__(self, cycle: tuple[Callable[..., Any], ...]) -> None:
        self.cycle = cycle
        names = " -> ".join(getattr(f, "__name__", repr(f)) for f in cycle)
        super().__init__(f"Depends dependency cycle detected: {names}.")


def _extract_depends(annotation: Any) -> Depends | None:
    """If `annotation` is `Annotated[T, ..., Depends(factory), ...]`, return the
    first `Depends` marker found in the metadata; else None.
    """
    if get_origin(annotation) is not Annotated:
        return None
    for meta in get_args(annotation)[1:]:
        if isinstance(meta, Depends):
            return meta
    return None


def _collect_annotated_deps(fn: Callable[..., Any]) -> dict[str, Depends]:
    """Walk `fn`'s kwonly params; return `{name: Depends}` for each
    `Annotated[T, Depends(factory)]`. Resolves PEP-563 string annotations via
    `inspect.get_type_hints(include_extras=True)` so the `Annotated` wrapper
    survives.
    """
    sig = inspect.signature(fn)
    try:
        hints = get_type_hints(fn, include_extras=True)
    except (NameError, AttributeError, TypeError):
        hints = getattr(fn, "__annotations__", {}) or {}
    out: dict[str, Depends] = {}
    for name, param in sig.parameters.items():
        if param.kind != inspect.Parameter.KEYWORD_ONLY:
            continue
        anno = hints.get(name)
        if anno is None:
            continue
        dep = _extract_depends(anno)
        if dep is not None:
            out[name] = dep
    return out


def _factory_non_depends_kwonly(fn: Callable[..., Any]) -> list[str]:
    """Names of `fn`'s kwonly params that are NOT `Annotated[..., Depends(...)]`
    — these must be filled from `call_ctx` at resolve time.
    """
    sig = inspect.signature(fn)
    try:
        hints = get_type_hints(fn, include_extras=True)
    except (NameError, AttributeError, TypeError):
        hints = getattr(fn, "__annotations__", {}) or {}
    names: list[str] = []
    for name, param in sig.parameters.items():
        if param.kind != inspect.Parameter.KEYWORD_ONLY:
            continue
        if _extract_depends(hints.get(name)) is None:
            names.append(name)
    return names


async def _call_factory(factory: Callable[..., Any], kwargs: dict[str, Any]) -> Any:
    """Invoke `factory(**kwargs)`; await if it returned a coroutine."""
    result = factory(**kwargs)
    if inspect.isawaitable(result):
        return await result
    return result


async def resolve_annotated_deps(
    deps: dict[str, Depends],
    *,
    overrides: dict[Callable[..., Any], Callable[..., Any]] | None = None,
    call_ctx: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve `{param_name: Depends(factory)}` to `{param_name: value}`.

    - Each factory is invoked at most once per call when `use_cache=True`
      (default) — keyed by the *original* (non-overridden) factory callable.
    - Overrides map: `overrides[original_factory] = replacement_factory`.
    - Factories may have their own `Annotated[..., Depends(...)]` kwonly params
      — resolved recursively. Non-Depends kwonly params are filled from
      `call_ctx` (e.g. `connection: str`).
    - 3-color DFS over factories detects cycles and raises `DependsCycleError`.
    """
    overrides = overrides or {}
    call_ctx = call_ctx or {}
    cache: dict[Callable[..., Any], Any] = {}
    WHITE, GRAY, BLACK = 0, 1, 2  # noqa: N806
    color: dict[Callable[..., Any], int] = {}
    path: list[Callable[..., Any]] = []

    async def _resolve(dep: Depends) -> Any:
        original = dep.dependency
        factory = overrides.get(original, original)
        if dep.use_cache and original in cache:
            return cache[original]
        if color.get(original, WHITE) == GRAY:
            start = path.index(original)
            raise DependsCycleError((*tuple(path[start:]), original))
        color[original] = GRAY
        path.append(original)
        try:
            sub_deps = _collect_annotated_deps(factory)
            kwargs: dict[str, Any] = {name: await _resolve(d) for name, d in sub_deps.items()}
            for ctx_name in _factory_non_depends_kwonly(factory):
                if ctx_name in call_ctx:
                    kwargs.setdefault(ctx_name, call_ctx[ctx_name])
            value = await _call_factory(factory, kwargs)
        finally:
            path.pop()
            color[original] = BLACK
        if dep.use_cache:
            cache[original] = value
        return value

    return {name: await _resolve(dep) for name, dep in deps.items()}


__all__ = [
    "Depends",
    "DependsCycleError",
    "_collect_annotated_deps",
    "_factory_non_depends_kwonly",
    "resolve_annotated_deps",
]
