"""Built-in health probe — `_meta.health` tool + `@app.health_check` decorator.

Round-2 a2web feedback (item 10): every serious deployable service ships a
fast, no-side-effect probe. a2kit owns this so every consumer (a2web, a2db,
a2atlassian) answers the same shape and ops engineers know what to expect.

Opt-in via ``@app.health_check`` (the first decorator call auto-installs
the synthetic router). The tool is named ``_meta.health`` and is
excluded from ``list_tools`` by default — agents shouldn't see it in
their tool picker. The CLI exposes ``<app> health`` whose exit code
reflects the aggregated status (0 ok, non-zero degraded).
"""

from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from collections.abc import Callable

    from a2kit.packages.di.resolver import Resolver


_LOGGER = logging.getLogger("a2kit.health")

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


async def run_checks(
    registry: HealthRegistry,
    resolver: Resolver,
    *,
    version: str = "unknown",
) -> dict[str, Any]:
    """Aggregate every registered check; return the health-tool response shape.

    Resolves each check's DI kwargs via ``resolver`` the same way tool
    dispatch does, so checks can take ``state: AppState`` (or any other
    registered provider).

    Takes a :class:`Resolver`, not an ``App``: a health check needs only
    DI resolution, never the composition root. Narrowing the parameter
    keeps ``packages/health`` free of any dependency on ``a2kit.app``.
    ``version`` is supplied by the caller (see :func:`app_version`).
    """
    overall: Literal["ok", "degraded"] = "ok"
    entries: list[dict[str, Any]] = []
    for check in registry.checks:
        result = await _run_one_check(resolver, check)
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
        "version": version,
        "checks": entries,
    }


async def _run_one_check(resolver: Resolver, check: _RegisteredCheck) -> Any:
    """Resolve check kwargs via the resolver, then call the check.

    Health checks are not tool dispatches; they don't have wire kwargs.
    Routes through the v0.36 resolver so app-scope ``__aenter__`` runs
    on first resolution (lazy first-use). Health checks declaring a
    resource as a parameter trigger entry of that resource.
    """
    call_kwargs = await resolver.resolve_params(check.fn)
    if inspect.iscoroutinefunction(check.fn):
        return await check.fn(**call_kwargs)
    result = check.fn(**call_kwargs)
    if inspect.isawaitable(result):
        result = await result
    return result


def app_version(obj: Any) -> str:
    """Return ``obj.version`` as a string, or ``"unknown"``.

    ``a2kit.App`` does not declare a ``version`` attribute today;
    consumers may attach one ad-hoc. When absent the probe payload
    reports ``"unknown"`` — an explicit sentinel, not a silently
    swallowed AttributeError. Callers pass the result to
    :func:`run_checks` as its ``version`` argument.
    """
    version = getattr(obj, "version", None)
    if version is None:
        return "unknown"
    if not isinstance(version, str):
        msg = f"App.version must be a str (got {type(version).__name__}); the health probe stringifies as fallback"
        _LOGGER.warning(msg)
        return str(version)
    return version


__all__ = [
    "HEALTH_TOOL_NAME",
    "META_NAMESPACE_PREFIX",
    "HealthRegistry",
    "HealthResult",
    "app_version",
    "run_checks",
]
