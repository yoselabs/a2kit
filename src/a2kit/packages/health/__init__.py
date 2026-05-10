"""Built-in health probe — `_meta.health` tool + `@app.health_check` decorator.

Round-2 a2web feedback (item 10): every serious deployable service ships a
fast, no-side-effect probe. a2kit owns this so every consumer (a2web, a2db,
a2atlassian) answers the same shape and ops engineers know what to expect.

Opt-in via ``App(name, health_tool=True)``. The tool is named ``_meta.health``
and is excluded from ``list_tools`` by default — agents shouldn't see it in
their tool picker. The CLI exposes ``<app> health`` whose exit code reflects
the aggregated status (0 ok, non-zero degraded).
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from collections.abc import Callable

    from a2kit.app import App


META_NAMESPACE_PREFIX = "_meta."
HEALTH_TOOL_NAME = "_meta.health"


@dataclass(frozen=True)
class HealthResult:
    """Outcome of a single health check.

    ``status="ok"`` is the happy path. ``status="fail"`` plus ``reason``
    documents why a probe failed (sqlite missing, env var unset, etc.).
    Future-proofed: additional fields (latency_ms, last_checked) can be
    added without breaking the API.
    """

    status: Literal["ok", "fail"]
    reason: str | None = None

    @classmethod
    def ok(cls) -> HealthResult:
        return cls(status="ok")

    @classmethod
    def fail(cls, reason: str) -> HealthResult:
        return cls(status="fail", reason=reason)


@dataclass
class _RegisteredCheck:
    name: str
    fn: Callable[..., Any]


@dataclass
class HealthRegistry:
    """Per-App health-check store. Mounted as ``app._health`` when enabled."""

    enabled: bool = False
    checks: list[_RegisteredCheck] = field(default_factory=list)

    def register(self, fn: Callable[..., Any]) -> Callable[..., Any]:
        name = getattr(fn, "__name__", "<callable>")
        self.checks.append(_RegisteredCheck(name=name, fn=fn))
        return fn


async def run_checks(app: App) -> dict[str, Any]:
    """Aggregate every registered check; return the health-tool response shape.

    Resolves DI kwargs the same way tool dispatch does so checks can take
    ``state: AppState`` (or any other registered provider).
    """
    registry: HealthRegistry = app._health  # noqa: SLF001 -- intentional, registry is App-scoped
    overall: Literal["ok", "degraded"] = "ok"
    entries: list[dict[str, Any]] = []
    for check in registry.checks:
        result = await _run_one_check(app, check)
        if not isinstance(result, HealthResult):
            result = HealthResult.fail(f"check {check.name!r} returned {type(result).__name__}, expected HealthResult")
        entry: dict[str, Any] = {"name": check.name, "status": result.status}
        if result.reason is not None:
            entry["reason"] = result.reason
        entries.append(entry)
        if result.status == "fail":
            overall = "degraded"
    return {
        "status": overall,
        "version": _app_version(app),
        "checks": entries,
    }


async def _run_one_check(app: App, check: _RegisteredCheck) -> Any:
    """Resolve check kwargs via the App's dispatch hook, then call the check."""
    hook = app._dispatch_hook  # noqa: SLF001
    resolved_any: Any = hook(check.fn, {})
    if inspect.isawaitable(resolved_any):
        resolved_any = await resolved_any
    call_kwargs = dict(resolved_any)
    if inspect.iscoroutinefunction(check.fn):
        return await check.fn(**call_kwargs)
    result = check.fn(**call_kwargs)
    if inspect.isawaitable(result):
        result = await result
    return result


def _app_version(app: App) -> str:
    """Best-effort: the package version of the App's host module, else ``"unknown"``."""
    return getattr(app, "version", None) or "unknown"


__all__ = [
    "HEALTH_TOOL_NAME",
    "META_NAMESPACE_PREFIX",
    "HealthRegistry",
    "HealthResult",
    "run_checks",
]
