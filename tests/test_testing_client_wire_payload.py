"""Tests — TestClient.call_wire (round-6 friction 2).

`call_wire(tool, **kwargs)` returns the formatter-encoded payload that
production transports would put on the wire. Reads the cached
`descriptor.format_hint` so test/prod stay in lockstep.
"""

from __future__ import annotations

import asyncio
import json

from pydantic import BaseModel

import a2kit
from a2kit.testing import client


# --- JSON: scalar / dict / model return --- #


class _DictRouter(a2kit.Router):
    @a2kit.read()
    async def whoami(self) -> dict[str, str]:
        return {"name": "alice"}


def test_call_wire_json_dict() -> None:
    app = a2kit.App("t").add_router(_DictRouter())

    async def go() -> None:
        async with client(app) as c:
            wire = await c.call_wire("whoami")
            # wire is the JSON-encoded data; loadable round-trip.
            assert json.loads(wire) == {"name": "alice"}

    asyncio.run(go())


# --- TSV: list-of-models return --- #


class _Row(BaseModel):
    id: int
    label: str


class _ListRouter(a2kit.Router):
    @a2kit.read()
    async def rows(self) -> list[_Row]:
        return [_Row(id=1, label="a"), _Row(id=2, label="b")]


def test_call_wire_tsv_for_list_of_models() -> None:
    app = a2kit.App("t").add_router(_ListRouter())

    async def go() -> None:
        async with client(app) as c:
            wire = await c.call_wire("rows")
            # TSV: header + rows separated by tabs and newlines.
            assert "id\tlabel" in wire
            assert "1\ta" in wire
            assert "2\tb" in wire

    asyncio.run(go())


# --- invoke vs call_wire — different surfaces --- #


def test_invoke_returns_python_value_while_call_wire_returns_encoded() -> None:
    app = a2kit.App("t").add_router(_DictRouter())

    async def go() -> None:
        async with client(app) as c:
            value = await c.invoke("whoami")
            assert value == {"name": "alice"}  # raw Python
            wire = await c.call_wire("whoami")
            assert isinstance(wire, str)  # JSON-encoded
            assert "alice" in wire

    asyncio.run(go())


# --- format auto-detection: change return annotation, wire flips --- #


class _Model(BaseModel):
    x: int


class _ScalarRouter(a2kit.Router):
    @a2kit.read()
    async def model(self) -> _Model:
        return _Model(x=42)


def test_call_wire_picks_json_for_single_model() -> None:
    app = a2kit.App("t").add_router(_ScalarRouter())

    async def go() -> None:
        async with client(app) as c:
            wire = await c.call_wire("model")
            assert json.loads(wire) == {"x": 42}

    asyncio.run(go())
