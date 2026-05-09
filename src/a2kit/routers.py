from __future__ import annotations

import functools
import inspect
import re
from typing import TYPE_CHECKING, Any, cast

from a2kit.metadata import A2KitMeta, EnricherFn, get_meta, set_meta

if TYPE_CHECKING:
    from collections.abc import Callable


def _wrap_with_enricher(fn: Callable[..., Any], enricher: EnricherFn) -> Callable[..., Any]:
    """Generic try/except → enricher(exc, tool_name) wrap. Protocol-neutral."""
    tool_name = getattr(fn, "__name__", "")

    if inspect.iscoroutinefunction(fn):

        @functools.wraps(fn)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return await fn(*args, **kwargs)
            except Exception as exc:
                raise enricher(exc, tool_name) from exc

        meta = get_meta(fn)
        if meta is not None:
            set_meta(async_wrapper, meta)
        return async_wrapper

    @functools.wraps(fn)
    def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            raise enricher(exc, tool_name) from exc

    meta = get_meta(fn)
    if meta is not None:
        set_meta(sync_wrapper, meta)
    return cast("Callable[..., Any]", sync_wrapper)


def _slugify(name: str) -> str:
    if name.endswith("Router") and name != "Router":
        name = name[: -len("Router")]
    s = re.sub(r"(?<!^)(?=[A-Z])", "-", name).lower()
    return re.sub(r"[^a-z0-9-]+", "-", s).strip("-") or name.lower()


class Router:
    name: str | None = None

    def __init__(self, name: str | None = None) -> None:
        self.slug = _slugify(name or self.name or type(self).__name__)
        self._tools: list[Callable[..., Any]] = []
        for fn in self._collect_methods():
            meta = get_meta(fn)
            if meta is not None and meta.router_slug is None:
                set_meta(
                    fn,
                    A2KitMeta(
                        tool_name=meta.tool_name,
                        verb=meta.verb,
                        tags=meta.tags,
                        annotations=meta.annotations,
                        router_slug=self.slug,
                        list_view=meta.list_view,
                        enricher=meta.enricher,
                        context_param_name=meta.context_param_name,
                        report_type=meta.report_type,
                        report_schema=meta.report_schema,
                    ),
                )
            self._tools.append(fn)

    def _collect_methods(self) -> list[Callable[..., Any]]:
        out: list[Callable[..., Any]] = []
        for attr in type(self).__dict__.values():
            if callable(attr) and get_meta(attr) is not None:
                out.append(attr)
        return out

    def tools(self) -> list[Callable[..., Any]]:
        """Return tool callables wrapped with their per-tool enricher (if any)."""
        out: list[Callable[..., Any]] = []
        for fn in self._tools:
            meta = get_meta(fn)
            enricher = meta.enricher if meta is not None else None
            out.append(_wrap_with_enricher(fn, enricher) if enricher is not None else fn)
        return out


class RouterRegistry:
    def __init__(self) -> None:
        self._routers: list[Router] = []

    def add(self, router: Router) -> None:
        self._routers.append(router)

    def all(self) -> list[Router]:
        return list(self._routers)

    def tools(self) -> list[Callable[..., Any]]:
        out: list[Callable[..., Any]] = []
        for r in self._routers:
            out.extend(r.tools())
        return out
