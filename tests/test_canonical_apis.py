"""End-to-end coverage of the documented canonical API call shapes.

Sister gate to ``tests/test_readme_symbol_drift.py``. The drift gate
catches references to symbols that don't exist; this file catches
shape regressions where a documented call signature changes
underneath the consumer (e.g. positional/keyword shift, renamed
parameter, return-type collapse).

Each test exercises exactly one documented shape end-to-end against a
small fixture app. Per ``canonical-api-drift-gate``, failure messages
point at the README claim the test pins.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from pydantic import BaseModel

import a2kit
from a2kit.testing import client


class _Echo(BaseModel):
    payload: str


class _ResourceForFactoryTest:
    pass


def _make_resource_for_factory_test() -> _ResourceForFactoryTest:
    return _ResourceForFactoryTest()


class _BaseForOverride:
    pass


class _SubForOverride(_BaseForOverride):
    pass


def _make_sub_for_override() -> _SubForOverride:
    return _SubForOverride()


class _Item(BaseModel):
    id: int


class _Router(a2kit.Router):
    slug = "x"

    @a2kit.read()
    async def echo(self, *, payload: str) -> _Echo:
        return _Echo(payload=payload)


def _build_app() -> a2kit.App:
    return a2kit.App("canonical-apis").add_router(_Router())


# --- TestClient call shapes --- #


def test_testclient_invoke_returns_tool_value() -> None:
    """README claims ``await c.invoke("tool", **kwargs)`` returns the tool's value."""
    app = _build_app()

    async def go() -> Any:
        async with client(app) as c:
            return await c.invoke("x_echo", payload="hi")

    result = asyncio.run(go())
    # FastMCP synthesizes a field-equivalent type (not _Echo itself).
    assert result.payload == "hi"


def test_testclient_call_wire_returns_wire_envelope() -> None:
    """README claims ``await c.call_wire("tool", **kwargs)`` returns raw wire."""
    app = _build_app()

    async def go() -> Any:
        async with client(app) as c:
            return await c.call_wire("x_echo", payload="hi")

    wire = asyncio.run(go())
    # call_wire returns the raw fastmcp result with .data / .content fields.
    assert wire is not None


def test_testclient_tools_listing() -> None:
    """README claims ``c.tools()`` returns descriptors."""
    app = _build_app()

    async def go() -> list[Any]:
        async with client(app) as c:
            return c.tools()

    descs = asyncio.run(go())
    names = [d.name for d in descs]
    assert "x_echo" in names


def test_testclient_renamed_call_raises_typeerror() -> None:
    """v0.33 rename: ``c.call`` is gone; access raises TypeError with hint."""
    from a2kit.packages.testing.client import TestClient  # noqa: N814,F401 -- canonical type name

    app = _build_app()
    c = TestClient(app)
    with pytest.raises(TypeError):
        _ = c.call  # noqa: B018


# --- App call shapes --- #


def test_app_singleton_class_form() -> None:
    """README claims ``app.provide(SomeClass)`` registers under the class."""

    class _Resource:
        pass

    app = a2kit.App("x")
    app.provide(_Resource)
    assert _Resource in app.provider_map()


def test_app_singleton_factory_form() -> None:
    """README claims ``app.provide(factory)`` registers under the return type."""
    app = a2kit.App("x")
    app.provide(_make_resource_for_factory_test)
    assert _ResourceForFactoryTest in app.provider_map()


def test_app_singleton_explicit_base_form() -> None:
    """README claims ``app.provide(BaseClass, factory)`` registers under base."""
    app = a2kit.App("x")
    app.provide(_BaseForOverride, _make_sub_for_override)
    assert _BaseForOverride in app.provider_map()
    assert _SubForOverride not in app.provider_map()


def test_app_lifespan_kwarg_removed() -> None:
    """v0.35 removal: ``App(lifespan=cm)`` raises TypeError with hint."""
    with pytest.raises(TypeError):
        a2kit.App("x", lifespan=None)  # type: ignore[call-arg]


def test_app_health_tool_kwarg_removed() -> None:
    """v0.35 removal: ``App(health_tool=True)`` raises TypeError with hint."""
    with pytest.raises(TypeError):
        a2kit.App("x", health_tool=True)  # type: ignore[call-arg]


# --- Verb decorator call shapes --- #


class _VerbDemoRouter(a2kit.Router):
    """Module-scope Router fixture for the verb-decorator coverage test."""

    slug = "_verbs"

    @a2kit.read()
    async def r(self) -> dict:
        return {}

    @a2kit.write()
    async def w(self) -> dict:
        return {}

    @a2kit.list_()
    async def lst(self) -> list[_Item]:
        return []


def test_verb_decorators_decorate_methods() -> None:
    """README claims ``@a2kit.read()``, ``@a2kit.write()``, ``@a2kit.list_()`` decorate methods."""
    app = a2kit.App("x").add_router(_VerbDemoRouter())
    names = [d.name for d in app.tools()]
    assert names == ["_verbs_r", "_verbs_w", "_verbs_lst"]


def test_router_subclass_with_slug_and_tools() -> None:
    """README claims ``class R(a2kit.Router): slug = "x"; tools = (...)`` works."""

    class _R(a2kit.Router):
        slug = "demo"

        @a2kit.read()
        async def f(self) -> dict:
            return {"ok": True}

    app = a2kit.App("x").add_router(_R())
    assert any(d.name == "demo_f" for d in app.tools())
