"""Mirror tests for the ``visibility`` decorator kwarg (replaces ``Surface``)."""

from __future__ import annotations

import a2kit
from a2kit.metadata import get_meta
from a2kit.routers import Router


def test_default_decorator_visibility_is_none() -> None:
    """Without `visibility=`, the decorator stamps None (inherit from router)."""

    @a2kit.read()
    async def f() -> dict[str, int]:
        return {"k": 1}

    meta = get_meta(f)
    assert meta is not None
    assert meta.extras.visibility is None


def test_explicit_cli_preserved() -> None:
    @a2kit.read(visibility="cli")
    async def f() -> dict[str, int]:
        return {"k": 1}

    meta = get_meta(f)
    assert meta is not None
    assert meta.extras.visibility == "cli"


def test_explicit_hidden_preserved() -> None:
    @a2kit.write(visibility="hidden")
    async def f() -> dict[str, int]:
        return {"k": 1}

    meta = get_meta(f)
    assert meta is not None
    assert meta.extras.visibility == "hidden"


def test_list_decorator_carries_visibility() -> None:
    @a2kit.list_(visibility="cli")
    async def f() -> list[dict[str, int]]:
        return [{"k": 1}]

    meta = get_meta(f)
    assert meta is not None
    assert meta.extras.visibility == "cli"


def test_tool_decorator_carries_visibility() -> None:
    from a2kit.tool import tool as tool_decorator

    @tool_decorator(visibility="hidden")
    async def f() -> dict[str, int]:
        return {"k": 1}

    meta = get_meta(f)
    assert meta is not None
    assert meta.extras.visibility == "hidden"


def test_router_class_attr_provides_default() -> None:
    """Router.visibility class attr fills None per-tool kwarg at __init__ time."""

    class _R(Router):
        slug = "r"
        visibility = "cli"

        @a2kit.read()
        async def ping(self) -> dict[str, int]:
            return {"k": 1}

        tools = (ping,)

    router = _R()
    fn = router.bound_tools()[0]
    meta = get_meta(fn)
    assert meta is not None
    assert meta.extras.visibility == "cli"


def test_per_tool_kwarg_overrides_router_default() -> None:
    """Explicit per-tool visibility wins over Router.visibility."""

    class _R(Router):
        slug = "r"
        visibility = "cli"

        @a2kit.read(visibility="all")
        async def public_status(self) -> dict[str, int]:
            return {"k": 1}

        tools = (public_status,)

    router = _R()
    fn = router.bound_tools()[0]
    meta = get_meta(fn)
    assert meta is not None
    assert meta.extras.visibility == "all"


def test_router_default_visibility_all() -> None:
    """Router with no visibility class attr defaults to 'all'."""

    class _R(Router):
        slug = "r"

        @a2kit.read()
        async def ping(self) -> dict[str, int]:
            return {"k": 1}

        tools = (ping,)

    router = _R()
    fn = router.bound_tools()[0]
    meta = get_meta(fn)
    assert meta is not None
    assert meta.extras.visibility == "all"
