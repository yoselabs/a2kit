"""BDD: `Container.expose_as_fastapi_depends` (bridge-container-fastapi-depends)."""

from __future__ import annotations

import pytest

from a2kit.packages.di import Container


class _Database:
    pass


class TestExposeAsFastapiDepends:
    @pytest.mark.asyncio
    async def test_resolver_outside_scope_raises(self) -> None:
        c = Container()
        c.provide(_Database, _Database)
        resolver = c.expose_as_fastapi_depends(_Database)
        with pytest.raises(RuntimeError, match="outside call_scope"):
            await resolver()

    def test_cache_returns_same_callable_per_type(self) -> None:
        c = Container()
        c.provide(_Database, _Database)
        first = c.expose_as_fastapi_depends(_Database)
        second = c.expose_as_fastapi_depends(_Database)
        assert first is second

    @pytest.mark.asyncio
    async def test_resolver_inside_scope_returns_instance(self) -> None:
        from a2kit.packages.di import _a2kit_request_scope

        c = Container()
        c.provide(_Database, _Database)
        resolver = c.expose_as_fastapi_depends(_Database)
        async with c as root:
            child = root.child()
            async with child as scope:
                token = _a2kit_request_scope.set(scope)
                try:
                    out = await resolver()
                    assert isinstance(out, _Database)
                finally:
                    _a2kit_request_scope.reset(token)
