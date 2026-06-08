"""BDD — MCP wire format `structured_output` mode (ADR 0022 / runtime-config).

Default (False) emits dual-channel per MCP spec backwards-compatibility:
structuredContent + serialized JSON in content[]. With True, structured
stays canonical and content[] is replaced with a short type-identifying
marker — saves duplicate JSON on hosts that forward structuredContent.
Error path is unaffected.
"""

from __future__ import annotations

import json
from typing import Annotated

import pytest
from pydantic import BaseModel

import a2kit
from a2effect import AppError, Raises
from a2kit.config import A2kitConfig, McpConfig
from a2kit.packages.mcp import build_mcp_server
from a2kit.testing import app_of


@pytest.fixture(autouse=True)
def _clear_a2kit_env(monkeypatch: pytest.MonkeyPatch) -> None:
    import os

    for k in list(os.environ):
        if k.startswith("A2KIT_"):
            monkeypatch.delenv(k, raising=False)


class _Memory(BaseModel):
    id: str
    title: str


class _NotFound(AppError):
    kind = "input"
    http_status = 404


class _R(a2kit.Router):
    slug = "mem"

    @a2kit.read()
    async def fetch(self, *, id: str) -> Annotated[_Memory, Raises(_NotFound)]:
        if id == "missing":
            raise _NotFound(f"memory {id!r} not found")
        return _Memory(id=id, title="hello")


def _build(cfg: A2kitConfig | None = None) -> a2kit.App:
    return app_of("strict-wire-test", _R(), config=cfg)


# ----- Default mode (False): spec-compliant dual emit -------------------- #


async def test_default_mode_emits_dual_content() -> None:
    from fastmcp import Client

    server = build_mcp_server(_build(), code_mode=False)
    async with Client(server) as client:
        result = await client.call_tool("mem_fetch", {"id": "x"})

    # content[].text carries serialized JSON of the model dump
    assert result.content
    payload = json.loads(result.content[0].text)
    assert payload == {"id": "x", "title": "hello"}

    # structured_content also carries the dump
    assert result.structured_content
    sc_inner = result.structured_content.get("result", result.structured_content)
    assert sc_inner == {"id": "x", "title": "hello"}


# ----- Strict mode (True): content marker only --------------------------- #


async def test_strict_mode_via_env_emits_marker(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastmcp import Client

    monkeypatch.setenv("A2KIT_MCP__STRUCTURED_OUTPUT", "true")
    server = build_mcp_server(_build(), code_mode=False)
    async with Client(server) as client:
        result = await client.call_tool("mem_fetch", {"id": "x"})

    # content[].text is a short marker, NOT the full payload
    assert result.content
    text = result.content[0].text
    assert "hello" not in text  # no payload duplication
    assert len(text) < 60  # genuinely short

    # structured_content carries the canonical payload
    assert result.structured_content
    sc_inner = result.structured_content.get("result", result.structured_content)
    assert sc_inner == {"id": "x", "title": "hello"}


async def test_strict_mode_via_explicit_config_emits_marker() -> None:
    from fastmcp import Client

    cfg = A2kitConfig(mcp=McpConfig(structured_output=True))
    server = build_mcp_server(_build(cfg), code_mode=False)
    async with Client(server) as client:
        result = await client.call_tool("mem_fetch", {"id": "x"})

    text = result.content[0].text
    assert "hello" not in text
    assert result.structured_content


# ----- Error path is unaffected by the setting --------------------------- #


async def test_error_path_unaffected_in_default_mode() -> None:
    from fastmcp import Client

    server = build_mcp_server(_build(), code_mode=False)
    async with Client(server) as client:
        result = await client.call_tool("mem_fetch", {"id": "missing"}, raise_on_error=False)

    assert result.is_error
    # error envelope on structured_content
    assert result.structured_content
    env = result.structured_content.get("error")
    assert env is not None
    assert env["type"] == "_NotFound"
    assert env["kind"] == "input"


async def test_error_path_unaffected_in_strict_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastmcp import Client

    monkeypatch.setenv("A2KIT_MCP__STRUCTURED_OUTPUT", "true")
    server = build_mcp_server(_build(), code_mode=False)
    async with Client(server) as client:
        result = await client.call_tool("mem_fetch", {"id": "missing"}, raise_on_error=False)

    assert result.is_error
    # error envelope still present in structured
    assert result.structured_content
    env = result.structured_content.get("error")
    assert env is not None
    assert env["type"] == "_NotFound"
