"""Typed-extras model (``A2KitMetaExtras``) coverage.

R4 replaces the open ``A2KitMeta.extra: dict[str, Any]`` slot with a typed
``A2KitMeta.extras: A2KitMetaExtras`` pydantic model. Verb decorators and
routers stamp named attributes; readers access them by name.
"""

from __future__ import annotations

import a2kit
from a2kit.metadata import A2KitMetaExtras, get_meta, stage_extra
from a2kit.surface import Surface


def test_default_extras_has_all_fields_none() -> None:
    extras = A2KitMetaExtras()
    assert extras.report_type is None
    assert extras.report_schema is None
    assert extras.router_slug is None
    assert extras.surfaces is None
    assert extras.list_view is None


def test_verb_decorator_stamps_surfaces() -> None:
    @a2kit.read(surfaces=Surface.MCP)
    async def f() -> dict[str, int]:
        return {"k": 1}

    meta = get_meta(f)
    assert meta is not None
    assert meta.extras.surfaces == Surface.MCP


def test_list_decorator_stamps_list_view() -> None:
    @a2kit.list_("id", page_size=5)
    async def f() -> list[dict[str, int]]:
        return [{"id": 1}]

    meta = get_meta(f)
    assert meta is not None
    assert meta.extras.list_view is not None
    assert meta.extras.list_view.default_fields == ("id",)
    assert meta.extras.list_view.page_size == 5


def test_router_stamps_router_slug() -> None:
    class SampleRouter(a2kit.Router):
        @a2kit.read()
        async def ping(self) -> dict[str, int]:
            return {"x": 1}

    router = SampleRouter()
    fn = router.tools()[0]
    meta = get_meta(fn)
    assert meta is not None
    assert meta.extras.router_slug == "sample"


def test_stage_extra_writes_attribute_when_meta_already_stamped() -> None:
    @a2kit.read()
    async def f() -> dict[str, int]:
        return {"k": 1}

    stage_extra(f, "report_type", int)
    meta = get_meta(f)
    assert meta is not None
    assert meta.extras.report_type is int


def test_stage_extra_queues_when_no_meta_yet() -> None:
    async def f() -> dict[str, int]:
        return {"k": 1}

    stage_extra(f, "report_schema", {"type": "object"})
    # The pending dict is private; decorate to flush.
    decorated = a2kit.read()(f)
    meta = get_meta(decorated)
    assert meta is not None
    assert meta.extras.report_schema == {"type": "object"}
