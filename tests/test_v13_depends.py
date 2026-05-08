"""v0.13 Phase 1: Annotated[T, Depends(factory)] DI path.

The Depends marker + resolver coexist with the v0.12 Provider Protocol; this
file exercises only the new path (existing tests cover the legacy path).

Note: no `from __future__ import annotations` — the resolver inspects runtime
annotations via `typing.get_type_hints(include_extras=True)`. PEP 593 metadata
(`Depends(...)`) only survives that round-trip when the annotation evaluates
at runtime.
"""

import inspect
from typing import Annotated

import pytest

import a2kit
from a2kit.di import (
    Depends,
    DependsCycleError,
    _collect_annotated_deps,
    resolve_annotated_deps,
)


# ---- 1. Simple Annotated[Depends] resolves and is injected ----------------- #


class _Foo:
    def __init__(self, val: str = "foo") -> None:
        self.val = val


async def _make_foo() -> _Foo:
    return _Foo("made")


async def test_simple_annotated_depends_injects() -> None:
    """A tool kwonly param `Annotated[Foo, Depends(make_foo)]` resolves and is
    passed to the function body when the wrapper is called."""

    captured: dict[str, _Foo] = {}

    @a2kit.tool()
    async def my_tool(*, foo: Annotated[_Foo, Depends(_make_foo)]) -> dict:
        captured["foo"] = foo
        return {"val": foo.val}

    result = await my_tool()
    assert result == {"val": "made"}
    assert captured["foo"].val == "made"


# ---- 2. Transitive: factory A depends on factory B via Annotated ----------- #


class _Bar:
    def __init__(self, foo: _Foo) -> None:
        self.foo = foo


async def _make_bar(*, foo: Annotated[_Foo, Depends(_make_foo)]) -> _Bar:
    return _Bar(foo)


async def test_transitive_depends_resolves_chain() -> None:
    """A factory with its own `Annotated[..., Depends(...)]` kwonly param has
    that dep resolved recursively."""

    @a2kit.tool()
    async def my_tool(*, bar: Annotated[_Bar, Depends(_make_bar)]) -> dict:
        return {"val": bar.foo.val}

    assert await my_tool() == {"val": "made"}


# ---- 3. use_cache=True (default): same factory called once per call -------- #


async def test_use_cache_default_dedupes_within_one_call() -> None:
    """When two params share the same factory, it's invoked once per call
    (default `use_cache=True`)."""

    calls = {"n": 0}

    async def make_counted() -> _Foo:
        calls["n"] += 1
        return _Foo(f"call-{calls['n']}")

    async def take_first(*, foo: Annotated[_Foo, Depends(make_counted)]) -> _Foo:
        return foo

    @a2kit.tool()
    async def my_tool(
        *,
        a: Annotated[_Foo, Depends(make_counted)],
        b: Annotated[_Foo, Depends(take_first)],
    ) -> dict:
        return {"a": a.val, "b": b.val}

    out = await my_tool()
    a, b = out["a"], out["b"]
    # Both end up resolving make_counted; cache means single invocation.
    assert calls["n"] == 1
    assert a == b == "call-1"


# ---- 4. dependency_overrides: replace factory in App.dependency_overrides -- #


async def test_dependency_overrides_replaces_factory(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Setting `app.dependency_overrides[factory] = replacement` causes the
    replacement to be invoked instead at tool-call time."""

    class _Conn(a2kit.ConnectionConfig):
        url: str = "real"

    class FooRouter(a2kit.Router):
        pass

    @FooRouter.tool()
    async def my_tool(*, foo: Annotated[_Foo, Depends(_make_foo)]) -> dict:
        return {"val": foo.val}

    app = a2kit.App("test-overrides")
    app.connect(_Conn, config_dir=tmp_path)
    app.use(FooRouter)

    async def fake_make_foo() -> _Foo:
        return _Foo("override")

    app.dependency_overrides[_make_foo] = fake_make_foo

    # Apply routers so the wrapper is registered on the FastMCP server.
    app._ensure_routers_applied()
    target = next(t for t in app.server._tool_manager.list_tools() if t.name == "my_tool")
    result = await target.fn()
    assert result == {"val": "override"}


# ---- 5. Cycle detection: A depends on B which depends on A ----------------- #


async def test_cycle_detection_raises_dependscycleerror() -> None:
    """Annotated cycle A → B → A must raise DependsCycleError."""

    # Forward-declare with module-scope holders so each factory references the
    # other before both are defined.
    async def factory_a(*, b: Annotated[int, Depends(lambda: 0)]) -> int:  # placeholder, replaced below  # noqa: ARG001
        return 1

    async def factory_b(*, a: Annotated[int, Depends(factory_a)]) -> int:
        return a + 1

    # Patch factory_a's annotation to depend on factory_b — closes the cycle.
    factory_a.__annotations__["b"] = Annotated[int, Depends(factory_b)]

    deps = {"x": Depends(factory_a)}
    with pytest.raises(DependsCycleError):
        await resolve_annotated_deps(deps)


# ---- 6. Sync tool with Annotated[Depends] params raises at decoration ------ #


def test_sync_tool_with_depends_raises_at_decoration() -> None:
    """Depends-based DI is async-only; decorating a sync function with an
    Annotated[Depends] kwonly param raises TypeError immediately."""

    with pytest.raises(TypeError, match="async tool function"):

        @a2kit.tool()
        def sync_tool(*, foo: Annotated[_Foo, Depends(_make_foo)]) -> dict:
            return {"val": foo.val}


# ---- 7. Annotated[Depends] params hidden from published signature ---------- #


async def test_annotated_dep_hidden_from_wrapper_signature() -> None:
    """The Depends-injected kwonly param doesn't appear in the wrapper's
    published signature (so it doesn't leak into FastMCP schema or Click sub-
    commands)."""

    @a2kit.tool()
    async def my_tool(
        *,
        foo: Annotated[_Foo, Depends(_make_foo)],
        title: str = "default",
    ) -> dict:
        return {"v": f"{foo.val}-{title}"}

    sig = inspect.signature(my_tool)
    assert "foo" not in sig.parameters
    assert "title" in sig.parameters
    # And it still works end-to-end.
    assert await my_tool(title="t") == {"v": "made-t"}


# ---- 8. call_ctx forwarding: factory's `connection: str` is filled --------- #


async def test_call_ctx_forwards_non_depends_kwonly_to_factory() -> None:
    """A factory with a `connection: str` kwonly (non-Depends) gets the value
    from the resolver's `call_ctx`."""

    seen: dict[str, str] = {}

    async def make_with_ctx(*, connection: str) -> _Foo:
        seen["connection"] = connection
        return _Foo(connection)

    deps = _collect_annotated_deps(
        _build_target_for_call_ctx(make_with_ctx),
    )
    resolved = await resolve_annotated_deps(deps, call_ctx={"connection": "prod"})
    assert resolved["foo"].val == "prod"
    assert seen["connection"] == "prod"


def _build_target_for_call_ctx(factory):  # type: ignore[no-untyped-def]
    """Return a function with a kwonly param annotated `Annotated[Foo, Depends(factory)]`.
    Built dynamically so each test gets a fresh factory binding."""

    async def target(*, foo) -> _Foo:  # type: ignore[no-untyped-def]
        return foo

    target.__annotations__["foo"] = Annotated[_Foo, Depends(factory)]
    return target
