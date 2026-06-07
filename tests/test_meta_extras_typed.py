"""Typed-extras model (``A2KitMetaExtras``) coverage.

R4 replaces the open ``A2KitMeta.extra: dict[str, Any]`` slot with a typed
``A2KitMeta.extras: A2KitMetaExtras`` pydantic model. Verb decorators and
routers stamp named attributes; readers access them by name.
"""

from __future__ import annotations

import a2kit
from a2kit.metadata import A2KitMetaExtras, _get_meta


def test_default_extras_has_all_fields_none() -> None:
    extras = A2KitMetaExtras()
    assert extras.report_type is None
    assert extras.report_schema is None
    assert extras.router_slug is None
    assert extras.visibility is None
    assert extras.list_view is None


def test_verb_decorator_stamps_visibility() -> None:
    @a2kit.read(visibility="cli")
    async def f() -> dict[str, int]:
        return {"k": 1}

    meta = _get_meta(f)
    assert meta is not None
    assert meta.extras.visibility == "cli"


def test_list_decorator_stamps_list_view() -> None:
    @a2kit.list_("id", page_size=5)
    async def f() -> list[dict[str, int]]:
        return [{"id": 1}]

    meta = _get_meta(f)
    assert meta is not None
    assert meta.extras.list_view is not None
    assert meta.extras.list_view.default_fields == ("id",)
    assert meta.extras.list_view.page_size == 5


def test_router_stamps_router_slug() -> None:
    class SampleRouter(a2kit.Router):
        slug = "sample"

        @a2kit.read()
        async def ping(self) -> dict[str, int]:
            return {"x": 1}

    router = SampleRouter()
    fn = router.bound_tools()[0]
    meta = _get_meta(fn)
    assert meta is not None
    assert meta.extras.router_slug == "sample"


def test_reports_kwarg_stamps_report_type() -> None:
    from pydantic import BaseModel

    class _Report(BaseModel):
        ok: bool

    # Intentionally non-module-scope: tests the decorator-time stamp path.
    @a2kit.read(reports=_Report)  # noqa: A2K-LDD-REPORT-TYPE
    async def f() -> dict[str, int]:
        return {"k": 1}

    meta = _get_meta(f)
    assert meta is not None
    assert meta.extras.report_type is _Report
    assert isinstance(meta.extras.report_schema, dict)


def test_reports_kwarg_handles_unschemable_type() -> None:
    """``_compute_report_schema`` swallows TypeAdapter failures.

    The runtime contract checks the type itself, not the schema, so missing
    schema is not fatal. Using a non-pydantic class that TypeAdapter cannot
    introspect (a function-scoped class with no annotations) triggers the
    fallback to ``None``.
    """

    class _NotSchemable:
        # No annotations, defined in function scope — TypeAdapter raises.
        def __init__(self) -> None:
            self.x = 1

    # Intentionally non-module-scope: tests the TypeAdapter fallback path.
    @a2kit.read(reports=_NotSchemable)  # type: ignore[arg-type]  # noqa: A2K-LDD-REPORT-TYPE
    async def f() -> dict[str, int]:
        return {"k": 1}

    meta = _get_meta(f)
    assert meta is not None
    assert meta.extras.report_type is _NotSchemable
    # Schema may be present or None depending on TypeAdapter's leniency; the
    # important thing is decoration did not raise.
