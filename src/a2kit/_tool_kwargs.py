"""Public `ToolKwargs` TypedDict — for higher-order decorator factories.

Promoted to public surface in v0.7. Authors building custom Router classmethods
(e.g. an `expensive` decorator) use `Unpack[ToolKwargs]` to keep the kwarg
contract type-checked end-to-end.

```python
from typing import Unpack
from a2kit import Cap, ToolKwargs

class MetricsRouter(a2kit.Router):
    @classmethod
    def expensive(cls, **kwargs: Unpack[ToolKwargs]):
        return cls.tool(capabilities={Cap.EXPENSIVE}, **kwargs)
```

`info_kwarg` is intentionally absent (removed in v0.7 — use
`Router.context.info()`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypedDict

if TYPE_CHECKING:
    from a2kit._capabilities import Capability
    from a2kit.connections import ConnectionStore
    from a2kit.enrichers import EnricherFn
    from a2kit.formatter import ListViewMode
    from a2kit.tokens import ResolverRegistry


class ToolKwargs(TypedDict, total=False):
    """Public TypedDict mirroring `@a2kit.tool(...)` kwargs.

    Use with `typing.Unpack` for custom decorator factories.
    """

    server: Any
    store: ConnectionStore[Any] | None
    connection: bool
    capabilities: set[Capability]
    write: bool
    streaming: bool
    tool_call_guard: bool
    otel: bool
    tool_name: str | None
    filter: ListViewMode | None
    fields: ListViewMode | None
    pagination: ListViewMode | None
    enricher: EnricherFn | None
    resolver_registry: ResolverRegistry | None
    cli: str | None


__all__ = ["ToolKwargs"]
