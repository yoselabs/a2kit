"""Router + RouterRegistry — class-based routing with auto-tagging.

Pulled out of scaffold.py in v0.11. The runtime decorators
(`_router_decorators`, `_router_state`) live in their own private modules
at the package root because they're imported by `tools.py` without going
through `scaffold` (avoids an import cycle).
"""

from __future__ import annotations

import builtins
import re
from collections.abc import (  # noqa: F401  # `Awaitable`/`Callable` used by `EnricherFn` resolution at Pydantic model-build time
    Awaitable,
    Callable,
    Iterable,
)
from pathlib import Path  # used by `Router.snapshot_dir`/`cassette_dir` at Pydantic model-build time
from typing import TYPE_CHECKING, Any, ClassVar, NamedTuple, Protocol, Unpack, runtime_checkable

from pydantic import BaseModel, ConfigDict, model_validator

from a2kit._capabilities import Cap, Capability
from a2kit._router_decorators import _make_decorator, _ToolBinding
from a2kit._router_state import _set_active
from a2kit.enrichers import EnricherFn

if TYPE_CHECKING:
    from a2kit._tool_kwargs import ToolKwargs

# `list` is a classmethod on `Router` (the verb-shaped decorator) which shadows
# the builtin in class-scope annotations. Use this alias for `list[...]` types
# inside the `Router` class body.
_list = builtins.list


_SLUG_RE = re.compile(r"^[a-z][a-z0-9_-]*$")
_CAMEL_BOUNDARY = re.compile(r"(?<!^)(?=[A-Z])")


def _slugify(class_name: str) -> str:
    """Convert a CamelCase class name (minus `Router` suffix) into a slug.

    `JiraConfluenceRouter` → `jira-confluence`
    `WidgetsRouter`        → `widgets`
    `Router`               → `""` (caller must validate / supply explicit name).
    """
    base = class_name.removesuffix("Router")
    if not base:
        return ""
    parts = _CAMEL_BOUNDARY.split(base)
    return "-".join(p.lower() for p in parts if p)


class Router(BaseModel):
    """Pydantic-modeled router with v0.6 ergonomics.

    Subclass it; the slug `name` is auto-derived from the class name (strip
    `Router` suffix, hyphenate CamelCase, lowercase). Override with explicit
    `name="..."` if needed.

    Use `@MyRouter.read/.write/.tool` classmethod decorators to bind tools.
    `register_read` / `register_write` walk `cls._tools` by default; override
    them for imperative dynamic-tool registration (escape hatch).

    `name` is auto-tagged onto every registered tool (unless `auto_tag=False`).

    v0.15: `Router` is no longer Generic over a connection type and no longer
    carries a `store` field. Connections live in `App.connect()` + the
    `Annotated[T, Depends(get_conn)]` resolver. Routers stay focused on
    grouping tools and contributing an enricher.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=False, extra="forbid")

    name: str = ""

    capabilities: ClassVar[set[Capability]] = set()
    read_capabilities: ClassVar[set[Capability]] = {Cap.READ}
    write_capabilities: ClassVar[set[Capability]] = {Cap.WRITE}

    enricher: EnricherFn | None = None

    snapshot_dir: Path | None = None
    cassette_dir: Path | None = None
    default: bool = True
    auto_tag: bool = True

    _tools: ClassVar[_list[_ToolBinding]] = []

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls._tools = []

    @model_validator(mode="before")
    @classmethod
    def _default_name(cls, values: Any) -> Any:
        """Auto-derive `name` from the class name when not explicitly provided."""
        if isinstance(values, dict) and not values.get("name"):
            slug = _slugify(cls.__name__)
            if slug and _SLUG_RE.match(slug):
                values["name"] = slug
        return values

    @model_validator(mode="after")
    def _validate_slug(self) -> Router:
        if not _SLUG_RE.match(self.name):
            msg = f"Router.name {self.name!r} must match pattern {_SLUG_RE.pattern}"
            raise ValueError(msg)
        return self

    @classmethod
    def tool(cls, **kwargs: Unpack[ToolKwargs]) -> Any:
        """Underlying primitive — register a tool on this router with explicit caps."""
        return _make_decorator(cls, mode="tool", decorator_kwargs=dict(**kwargs))

    @classmethod
    def read(cls, **kwargs: Unpack[ToolKwargs]) -> Any:
        """Register a read-mode tool. Effective caps include `cls.read_capabilities`."""
        return _make_decorator(cls, mode="read", decorator_kwargs=dict(**kwargs))

    @classmethod
    def write(cls, **kwargs: Unpack[ToolKwargs]) -> Any:
        """Register a write-mode tool. Effective caps include `cls.write_capabilities`."""
        return _make_decorator(cls, mode="write", decorator_kwargs=dict(**kwargs))

    @classmethod
    def list(cls, **kwargs: Unpack[ToolKwargs]) -> Any:
        """Register a list-shaped tool. Effective caps include `cls.read_capabilities`;
        list-view kit (filter / fields / pagination) defaults to Local. Author
        kwargs override the verb defaults."""
        return _make_decorator(cls, mode="list", decorator_kwargs=dict(**kwargs))

    def register_read(self, server: Any) -> None:
        """Walk `cls._tools` (mode in {'read','tool','list'}) and register on `server`."""
        self._apply_bindings(server, mode_filter={"read", "tool", "list"})

    def register_write(self, server: Any) -> None:
        """Walk `cls._tools` (mode='write') and register on `server`."""
        self._apply_bindings(server, mode_filter={"write"})

    def _apply_bindings(self, server: Any, *, mode_filter: set[str]) -> None:
        """Iterate `cls._tools`, call `@a2kit.tool(...)` with merged kwargs."""
        from a2kit.formatter import Local  # noqa: PLC0415
        from a2kit.tools import tool as _tool_decorator  # noqa: PLC0415

        # v0.15: enricher resolution at the router-binding layer is
        # `router.enricher > app.enricher`. Tool-level overrides happen
        # later inside `_make_decorator`.
        default_enricher: Any = self.enricher
        if default_enricher is None:
            default_enricher = getattr(self, "_a2kit_app_enricher", None)
        for binding in self._tools:
            if binding.mode not in mode_filter:
                continue
            merged: dict[str, Any] = {
                "server": server,
                "enricher": default_enricher,
                "app_dependency_overrides": getattr(self, "_a2kit_dependency_overrides", None),
            }
            merged.update(binding.decorator_kwargs)
            extra_caps: set[Capability] = set(binding.capabilities)
            if binding.mode == "read":
                extra_caps |= self.__class__.read_capabilities
            elif binding.mode == "write":
                extra_caps |= self.__class__.write_capabilities
                merged.setdefault("write", True)
            elif binding.mode == "list":
                # v0.12: list-shaped tools get read caps + list-view kit
                # defaulted to Local. Author kwargs (already merged in) win.
                extra_caps |= self.__class__.read_capabilities
                merged.setdefault("filter", Local)
                merged.setdefault("fields", Local)
                merged.setdefault("pagination", Local)
            existing_caps = set(merged.get("capabilities", set()) or set())
            merged["capabilities"] = existing_caps | extra_caps
            _tool_decorator(**merged)(binding.fn)


@runtime_checkable
class _RegisterableRouter(Protocol):
    """Internal Protocol — what `RouterRegistry.apply` actually needs from each entry.

    Both `Router` instances and decorator-registered classes satisfy this
    structurally.
    """

    def register_read(self, server: Any) -> None: ...

    def register_write(self, server: Any) -> None: ...


class _RouterEntry(NamedTuple):
    """One row in `RouterRegistry._routers`."""

    name: str
    default: bool
    item: Any  # `Router` instance or decorator-registered class — duck-typed


class RouterRegistry:
    """Registry of routers — supports `Router` instances and class-decorator form."""

    def __init__(self) -> None:
        self._routers: list[_RouterEntry] = []

    def add(self, router: Router) -> Router:
        """Register a `Router` instance. Returns the instance for chaining."""
        self._routers.append(_RouterEntry(router.name, router.default, router))
        return router

    def router(self, name: str, *, default: bool = True) -> Any:
        """Register a router class via decorator."""

        def decorator(cls: Any) -> Any:
            self._routers.append(_RouterEntry(name, default, cls))
            return cls

        return decorator

    def names(self) -> list[str]:
        """Return ordered router names."""
        return [entry.name for entry in self._routers]

    def ephemeral_store_pairs(self, store: Any) -> list[tuple[str, Any]]:
        """Pair each router with `store` for ephemeral-connection registration.

        v0.19: renamed from ``routers_with_stores(fallback_store=...)`` to
        spell out the actual purpose. Routers no longer own per-router stores
        (since v0.15), so this is a flat 1:1 fan-out used only by the
        ``--register`` CLI path. Returns ``[]`` when ``store`` is ``None``.
        """
        if store is None:
            return []
        return [(entry.name, store) for entry in self._routers]

    def defaults(self) -> set[str]:
        """Return the set of names enabled-by-default."""
        return {entry.name for entry in self._routers if entry.default}

    def apply(
        self,
        server: Any,
        *,
        enabled: Iterable[str] | None = None,
        include_writes: bool = False,
    ) -> list[str]:
        """Register read tools (always) and write tools (if `include_writes`).

        Sets the active-router thread-local before calling each register hook
        so the fat decorator can auto-tag.

        v0.19: dropped the `store` parameter — Routers no longer own a store,
        and the call sites that needed one have been migrated to
        `App.get_store(conn_type)` (contrib factories) or to the App-level
        single-store seam (ephemeral connections).
        """
        wanted = set(enabled) if enabled is not None else self.defaults()
        unknown = wanted - {entry.name for entry in self._routers}
        if unknown:
            msg = f"Unknown router(s): {sorted(unknown)}; available: {self.names()}"
            raise ValueError(msg)
        applied: list[str] = []
        for entry in self._routers:
            if entry.name not in wanted:
                continue
            item = entry.item
            router_obj = item if isinstance(item, Router) else None
            try:
                if router_obj is not None:
                    _set_active(router_obj, "read")
                if hasattr(item, "register_read"):
                    item.register_read(server)
                if include_writes and hasattr(item, "register_write"):
                    if router_obj is not None:
                        _set_active(router_obj, "write")
                    item.register_write(server)
            finally:
                _set_active(None, None)
            applied.append(entry.name)
        return applied


__all__ = [
    "Router",
    "RouterRegistry",
    "_RegisterableRouter",
    "_RouterEntry",
    "_slugify",
]
