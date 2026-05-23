"""BDD: ``ToolDescriptor`` projection fields.

Covers the contract from ``openspec/changes/extend-descriptor-fields``:
``ToolDescriptor`` carries the projected tool shape so substrate adapters
read one immutable record instead of re-deriving from ``A2KitMeta``.

Container-dependent fields (``wire_param_names`` / ``lazy_param_names``)
are populated by ``defer-descriptor-materialization``; in this change they
default to ``None``.
"""

from __future__ import annotations

from typing import Any

import pytest
from mcp.types import ToolAnnotations
from pydantic import BaseModel

import a2kit
from a2kit import ToolContext


class _Memory(BaseModel):
    id: str
    body: str


class TestDescriptorProjection:
    def test_ctx_param_name_projected_when_present(self):
        class R(a2kit.Router):
            slug = "r"

            @a2kit.read()
            async def fetch(self, *, ctx: ToolContext, id: str) -> _Memory:  # noqa: ARG002
                return _Memory(id=id, body="x")

            tools = (fetch,)

        d = a2kit.App("t").add_router(R()).tools()[0]
        assert d.ctx_param_name == "ctx"

    def test_ctx_param_name_none_when_absent(self):
        class R(a2kit.Router):
            slug = "r"

            @a2kit.read()
            async def fetch(self, *, id: str) -> _Memory:
                return _Memory(id=id, body="x")

            tools = (fetch,)

        d = a2kit.App("t").add_router(R()).tools()[0]
        assert d.ctx_param_name is None

    def test_timeout_projected(self):
        class R(a2kit.Router):
            slug = "r"

            @a2kit.read(timeout=5.0)
            async def fetch(self, *, id: str) -> _Memory:
                return _Memory(id=id, body="x")

            tools = (fetch,)

        d = a2kit.App("t").add_router(R()).tools()[0]
        assert d.timeout == 5.0

    def test_timeout_none_by_default(self):
        class R(a2kit.Router):
            slug = "r"

            @a2kit.read()
            async def fetch(self, *, id: str) -> _Memory:
                return _Memory(id=id, body="x")

            tools = (fetch,)

        d = a2kit.App("t").add_router(R()).tools()[0]
        assert d.timeout is None

    def test_annotations_view_dict_shaped_and_immutable(self):
        class R(a2kit.Router):
            slug = "r"

            @a2kit.read(annotations=ToolAnnotations(readOnlyHint=True))
            async def fetch(self, *, id: str) -> _Memory:
                return _Memory(id=id, body="x")

            tools = (fetch,)

        d = a2kit.App("t").add_router(R()).tools()[0]
        assert d.annotations_view["readOnlyHint"] is True
        view: Any = d.annotations_view
        with pytest.raises(TypeError):
            view["readOnlyHint"] = False

    def test_annotations_view_defaults_for_read_verb(self):
        class R(a2kit.Router):
            slug = "r"

            @a2kit.read()
            async def fetch(self, *, id: str) -> _Memory:
                return _Memory(id=id, body="x")

            tools = (fetch,)

        d = a2kit.App("t").add_router(R()).tools()[0]
        # @a2kit.read() stamps default hints: readOnly=True, destructive=False, etc.
        assert d.annotations_view["readOnlyHint"] is True
        assert d.annotations_view["destructiveHint"] is False

    def test_metadata_view_exposes_verb(self):
        class R(a2kit.Router):
            slug = "r"

            @a2kit.list_("id")
            async def list_x(self) -> list[_Memory]:
                return []

            tools = (list_x,)

        d = a2kit.App("t").add_router(R()).tools()[0]
        assert d.metadata_view["verb"] == "list"

    def test_metadata_view_exposes_tags_and_ctx_name(self):
        class R(a2kit.Router):
            slug = "r"

            @a2kit.read()
            async def fetch(self, *, ctx: ToolContext, id: str) -> _Memory:  # noqa: ARG002
                return _Memory(id=id, body="x")

            tools = (fetch,)

        d = a2kit.App("t").add_router(R()).tools()[0]
        assert "read" in d.metadata_view["tags"]
        assert d.metadata_view["context_param_name"] == "ctx"

    def test_metadata_view_immutable(self):
        class R(a2kit.Router):
            slug = "r"

            @a2kit.read()
            async def fetch(self, *, id: str) -> _Memory:
                return _Memory(id=id, body="x")

            tools = (fetch,)

        d = a2kit.App("t").add_router(R()).tools()[0]
        view: Any = d.metadata_view
        with pytest.raises(TypeError):
            view["verb"] = "write"

    def test_container_dependent_fields_default_none(self):
        """``wire_param_names``/``lazy_param_names`` are sentinels until
        ``defer-descriptor-materialization`` populates them."""

        class R(a2kit.Router):
            slug = "r"

            @a2kit.read()
            async def fetch(self, *, id: str) -> _Memory:
                return _Memory(id=id, body="x")

            tools = (fetch,)

        d = a2kit.App("t").add_router(R()).tools()[0]
        assert d.wire_param_names is None
        assert d.lazy_param_names is None
