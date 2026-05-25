"""BDD scenarios for tool-descriptors / Raises field materialization."""

from __future__ import annotations

from typing import Annotated

import pytest
from a2effect import AppError, Raises

import a2kit


class NotFound(AppError):
    kind = "input"


class InvalidId(AppError):
    kind = "input"


class _Memory:
    pass


class _BadNonAppError(Exception):
    pass


def test_descriptor_raises_populated_from_annotation() -> None:
    class R(a2kit.Router):
        slug = "r1"

        @a2kit.read()
        async def fetch(self, *, id: str) -> Annotated[dict, Raises(NotFound, InvalidId)]:
            return {"id": id}

        tools = (fetch,)

    app = a2kit.App("t").add_router(R())
    desc = app.tools()[0]
    assert desc.raises == (NotFound, InvalidId)


def test_descriptor_raises_empty_when_no_annotation() -> None:
    class R(a2kit.Router):
        slug = "r2"

        @a2kit.read()
        async def fetch(self, *, id: str) -> dict:
            return {"id": id}

        tools = (fetch,)

    app = a2kit.App("t").add_router(R())
    assert app.tools()[0].raises == ()


def test_multiple_raises_markers_flatten_additively() -> None:
    class R(a2kit.Router):
        slug = "r3"

        @a2kit.read()
        async def fetch(self, *, id: str) -> Annotated[dict, Raises(NotFound), Raises(InvalidId)]:
            return {"id": id}

        tools = (fetch,)

    app = a2kit.App("t").add_router(R())
    assert set(app.tools()[0].raises) == {NotFound, InvalidId}


def test_non_app_error_in_raises_rejected_at_registration() -> None:
    class R(a2kit.Router):
        slug = "r4"

        @a2kit.read()
        async def fetch(self, *, id: str) -> Annotated[dict, Raises(_BadNonAppError)]:  # type: ignore[arg-type]
            return {"id": id}

        tools = (fetch,)

    with pytest.raises(TypeError, match="AppError subclass"):
        a2kit.App("t").add_router(R())


def test_return_type_strips_raises_for_format_inference() -> None:
    class R(a2kit.Router):
        slug = "r5"

        @a2kit.read()
        async def fetch(self, *, id: str) -> Annotated[str, Raises(NotFound)]:
            return id

        tools = (fetch,)

    desc = a2kit.App("t").add_router(R()).tools()[0]
    # The descriptor's return_type carries the bare type (str), not Annotated[...]
    assert desc.return_type is str
