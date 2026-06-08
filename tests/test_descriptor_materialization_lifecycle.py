"""BDD: build-time descriptor re-materialization (defer-descriptor-materialization).

`runtime.build(app)` SHALL re-materialise descriptors against the runtime
container, populating `wire_param_names` and `lazy_param_names`. Pre-build
access via `app.tools()` keeps the `None` sentinel for those fields.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

import a2kit
from a2kit.packages.di import Lazy
from a2kit.runtime import build
from a2kit.testing import app_of


class _Memory(BaseModel):
    id: str


class _Database:
    pass


class _Cache:
    pass


class TestBuildTimeMaterialization:
    def test_wire_param_names_excludes_container_provided(self):
        class R(a2kit.Router):
            slug = "r"

            @a2kit.read()
            async def fetch(self, *, db: _Database, id: str) -> _Memory:  # noqa: ARG002
                return _Memory(id=id)

        app = app_of("t", R())
        app.provide(_Database, _Database)
        runtime = build(app)
        d = runtime.descriptor_for("r_fetch")
        assert d.wire_param_names == frozenset({"id"})
        assert d.lazy_param_names == frozenset()

    def test_pre_build_descriptor_has_none_sentinels(self):
        class R(a2kit.Router):
            slug = "r"

            @a2kit.read()
            async def fetch(self, *, db: _Database, id: str) -> _Memory:  # noqa: ARG002
                return _Memory(id=id)

        app = app_of("t", R())
        app.provide(_Database, _Database)
        d = app.tools()[0]
        assert d.wire_param_names is None
        assert d.lazy_param_names is None

    def test_lazy_param_classified_as_lazy_not_wire(self):
        class R(a2kit.Router):
            slug = "r"

            @a2kit.read()
            async def warm(self, *, cache: Lazy[_Cache], id: str) -> _Memory:  # noqa: ARG002
                return _Memory(id=id)

        app = app_of("t", R())
        app.provide(_Cache, _Cache)
        runtime = build(app)
        d = runtime.descriptor_for("r_warm")
        assert d.lazy_param_names == frozenset({"cache"})
        assert "cache" not in (d.wire_param_names or set())
        assert d.wire_param_names == frozenset({"id"})

    def test_descriptor_for_raises_keyerror_on_miss(self):
        class R(a2kit.Router):
            slug = "r"

            @a2kit.read()
            async def fetch(self, *, id: str) -> _Memory:
                return _Memory(id=id)

        runtime = build(app_of("t", R()))
        with pytest.raises(KeyError):
            runtime.descriptor_for("does_not_exist")

    def test_descriptors_returns_tuple(self):
        class R(a2kit.Router):
            slug = "r"

            @a2kit.read()
            async def fetch(self, *, id: str) -> _Memory:
                return _Memory(id=id)

        runtime = build(app_of("t", R()))
        descs = runtime.descriptors()
        assert isinstance(descs, tuple)
        # Same object identity as descriptor_for lookup.
        assert descs[0] is runtime.descriptor_for("r_fetch") or any(
            d.name == "r_fetch" and d is runtime.descriptor_for("r_fetch") for d in descs
        )
