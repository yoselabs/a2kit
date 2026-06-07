"""``a2kit.runtime`` — the internal sealed runtime and the ``build()`` finisher seam.

Covers the `app-lifecycle` and `core-composition` capabilities post
`split-app-runtime`: a finisher's internal ``build(app)`` snapshots the
compose-phase ``App`` into an ``AppRuntime``; the ``AppRuntime`` is the
async context manager; post-build composition affects only future builds.
See ADR 0019 (supersedes ADR 0017).
"""

from __future__ import annotations

import pytest

import a2kit
from a2kit.runtime import AppRuntime, build


class _Res:
    """Async-CM resource that records enter/exit against a shared log."""

    def __init__(self, name: str, log: list[str]) -> None:
        self.name = name
        self.log = log

    async def __aenter__(self) -> _Res:
        self.log.append(f"enter:{self.name}")
        return self

    async def __aexit__(self, *_exc: object) -> None:
        self.log.append(f"exit:{self.name}")


class _ResA(_Res):
    pass


class _ResB(_Res):
    pass


class _ResC(_Res):
    pass


class _PerCall:
    """Per-call-scoped dependency."""


class _AppScopeNeedsPerCall:
    """App-scope factory that illegally depends on a per-call type."""

    def __init__(self, dep: _PerCall) -> None:
        self.dep = dep


class _Probe(a2kit.Router):
    slug = "probe"

    @a2kit.read()
    async def get(self) -> dict:
        return {"ok": True}


# --------------------------- AppRuntime lifecycle -------------------------- #


async def test_runtime_entry_does_not_enter_resources_eagerly() -> None:
    """Entering the AppRuntime does not enter app-scope resources."""
    log: list[str] = []
    app = a2kit.App("svc")
    app.provide(_ResA, lambda: _ResA("A", log))
    app.provide(_ResB, lambda: _ResB("B", log))

    async with build(app):
        pass

    assert log == [], f"no resource should have entered: {log!r}"


async def test_runtime_exit_unwinds_resolved_resources_lifo() -> None:
    """Resources resolved during the runtime's lifetime unwind in LIFO order."""
    log: list[str] = []
    app = a2kit.App("svc")
    app.provide(_ResA, lambda: _ResA("A", log))
    app.provide(_ResB, lambda: _ResB("B", log))
    app.provide(_ResC, lambda: _ResC("C", log))

    async with build(app) as runtime:
        await runtime._resolver.get(_ResA)
        await runtime._resolver.get(_ResB)
        await runtime._resolver.get(_ResC)

    assert log == [
        "enter:A",
        "enter:B",
        "enter:C",
        "exit:C",
        "exit:B",
        "exit:A",
    ], f"LIFO unwind broken: {log!r}"


async def test_runtime_lifespan_body_may_force_resolve() -> None:
    """The lifespan body may force-resolve a resource for start-time verification."""
    log: list[str] = []
    app = a2kit.App("svc")
    app.provide(_ResA, lambda: _ResA("A", log))

    async with build(app) as runtime:
        instance = await runtime._resolver.get(_ResA)
        assert isinstance(instance, _ResA)
        assert log == ["enter:A"], "force-resolve must enter the resource at start"


# ----------------------- build-snapshot isolation -------------------------- #


async def test_build_snapshot_is_isolated_from_later_mutation() -> None:
    """Mutating the App after build() does not reach the already-built runtime."""
    app = a2kit.App("svc")
    app.provide(int, lambda: 1)

    runtime_one = build(app)

    # Mutate the App after the first build.
    app.provide(str, lambda: "late")
    app.add_router(_Probe())

    assert not runtime_one._container.has_provider(str), "late provider leaked into a built runtime"
    assert all(r.slug != "probe" for r in runtime_one.routers()), "late router leaked into a built runtime"

    # A second build sees the mutation.
    runtime_two = build(app)
    assert runtime_two._container.has_provider(str), "second build missed the new provider"
    assert any(r.slug == "probe" for r in runtime_two.routers()), "second build missed the new router"


async def test_build_is_idempotent_on_a_runtime() -> None:
    """build() of an AppRuntime returns it unchanged — the multiplex-serve seam."""
    app = a2kit.App("svc")
    runtime = build(app)
    assert build(runtime) is runtime


# ----------------------- graph validation at build ------------------------- #


def test_build_rejects_scope_violation_before_producing_a_runtime() -> None:
    """build() runs graph validation; a scope violation raises before any runtime exists."""
    app = a2kit.App("svc")
    app.provide(_PerCall, per_call=True)
    app.provide(_AppScopeNeedsPerCall)

    with pytest.raises(TypeError, match="scope violation"):
        build(app)


def test_appruntime_is_not_exported_on_the_public_surface() -> None:
    """AppRuntime is internal — it is not reachable as ``a2kit.AppRuntime``."""
    assert not hasattr(a2kit, "AppRuntime")
    # It is importable from its owning module for framework / test code.
    assert AppRuntime.__module__ == "a2kit.runtime"
