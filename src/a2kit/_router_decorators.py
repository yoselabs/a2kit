"""Router decorator infrastructure — `@Router.read/.write/.tool`.

Each Router subclass owns a fresh `_tools: list[_ToolBinding]` (initialised in
`__init_subclass__`). The decorators record bindings; `RouterRegistry.apply()`
materialises them into FastMCP `server.tool()` registrations at runtime,
injecting Router-level DI (store, enricher, resolver_registry, ephemeral)
and the per-Router ContextVar accessor.

# Author seam:
# - `@MyRouter.read(connection_param="conn", capabilities={...})` — read-mode
#   sugar; effective caps = router.capabilities | router.read_capabilities |
#   binding.capabilities.
# - `@MyRouter.write(...)` — same, with `write_capabilities` + `write=True`.
# - `@MyRouter.tool(...)` — primitive; no read/write sugar.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from collections.abc import Callable


class _ToolBinding(BaseModel):
    """Recorded tool binding from a `@Router.read/.write/.tool` decorator call.

    Materialised at apply-time by walking `Router._tools`.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=False, extra="forbid")

    fn: Any
    decorator_kwargs: dict[str, Any]
    capabilities: set[str]
    mode: Literal["read", "write", "tool"]


def _make_decorator(
    router_cls: type,
    *,
    mode: Literal["read", "write", "tool"],
    decorator_kwargs: dict[str, Any],
) -> Callable[[Any], Any]:
    """Build a decorator that records a `_ToolBinding` on `router_cls`."""

    extra_caps: set[str] = set(decorator_kwargs.pop("capabilities", set()) or set())

    def decorator(fn: Any) -> Any:
        binding = _ToolBinding(
            fn=fn,
            decorator_kwargs=dict(decorator_kwargs),
            capabilities=set(extra_caps),
            mode=mode,
        )
        # `_tools` is declared on `Router`; subclasses inherit & re-init it via
        # `__init_subclass__`. Access through `getattr` keeps ty happy on a
        # plain `type` parameter.
        tools_list = getattr(router_cls, "_tools", None)
        if tools_list is None:  # pragma: no cover — Router base always sets it
            tools_list = []
            setattr(router_cls, "_tools", tools_list)  # noqa: B010
        tools_list.append(binding)
        return fn

    return decorator


__all__ = ["_ToolBinding", "_make_decorator"]
