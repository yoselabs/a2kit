"""BDD specs — the type-checking code-mode sandbox runtime.

The `A2kitSandboxProvider` type-checks LLM code against generated stubs
before executing it, retrying once on a type error; end-to-end the
`execute` tool gives sandbox code attribute access to `call_tool` results.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel

import a2kit
from a2kit.packages.codemode.runtime import A2kitSandboxProvider
from a2kit.packages.codemode.stubs import generate_stubs
from a2kit.packages.formatter import Page
from a2kit.packages.mcp import build_mcp_server
from a2kit.runtime import build


class Task(BaseModel):
    id: int
    title: str


class TestTypeChecking:
    """Requirement: Sandbox code is type-checked before execution."""

    def test_good_code_type_checks(self):
        stubs = generate_stubs([("get", Task)])
        assert A2kitSandboxProvider._type_check("1 + 1", stubs) is None

    def test_misnamed_field_is_rejected(self):
        stubs = generate_stubs([("get", Task)])
        bad = 'async def f():\n    r = await call_tool("get", {})\n    return r.titel\nawait f()'
        assert A2kitSandboxProvider._type_check(bad, stubs) is not None

    def test_hallucinated_tool_name_is_rejected(self):
        stubs = generate_stubs([("get", Task)])
        bad = 'await call_tool("ghost", {})'
        assert A2kitSandboxProvider._type_check(bad, stubs) is not None

    @pytest.mark.anyio
    async def test_no_sampling_means_a_type_error_fails_the_call(self):
        stubs = generate_stubs([("get", Task)])
        provider = A2kitSandboxProvider()
        bad = 'await call_tool("ghost", {})'
        # ctx is None — no retry possible; the call fails with the diagnostic
        with pytest.raises(Exception, match="type checker"):
            await provider._validate(bad, stubs, ctx=None)

    @pytest.mark.anyio
    async def test_a_type_error_triggers_exactly_one_retry(self):
        stubs = generate_stubs([("get", Task)])
        provider = A2kitSandboxProvider()
        bad = 'await call_tool("ghost", {})'

        class _Reply:
            text = "```python\n1 + 1\n```"

        class _FixCtx:
            async def sample(self, prompt: str) -> _Reply:
                return _Reply()

        # the retry returns type-clean code → validation succeeds
        validated = await provider._validate(bad, stubs, ctx=_FixCtx())
        assert validated.strip() == "1 + 1"

    @pytest.mark.anyio
    async def test_a_second_failure_fails_the_call(self):
        stubs = generate_stubs([("get", Task)])
        provider = A2kitSandboxProvider()
        bad = 'await call_tool("ghost", {})'

        class _BadReply:
            text = '```python\nawait call_tool("still_ghost", {})\n```'

        class _StillBadCtx:
            async def sample(self, prompt: str) -> _BadReply:
                return _BadReply()

        with pytest.raises(Exception, match="type checker"):
            await provider._validate(bad, stubs, ctx=_StillBadCtx())


class _SandboxRouter(a2kit.Router):
    slug = "sbx"

    @a2kit.read()
    async def get_task(self) -> Task:
        """A single record."""
        return Task(id=1, title="solo")

    @a2kit.read()
    async def list_tasks(self) -> Page[Task]:
        """A paginated result."""
        return Page[Task](
            items=[Task(id=1, title="a"), Task(id=2, title="b")],
            next_cursor=None,
        )


@pytest.fixture
def sandbox_app() -> a2kit.App:
    return a2kit.App("sandbox-runtime-test").add_router(_SandboxRouter())


def _text(result: Any) -> str:
    return "\n".join(getattr(b, "text", "") for b in result.content)


class TestExecuteEndToEnd:
    """call_tool results support attribute access inside the real sandbox."""

    @pytest.mark.anyio
    async def test_call_tool_result_supports_attribute_access(self, sandbox_app: a2kit.App) -> None:
        runtime = build(sandbox_app)
        server = build_mcp_server(runtime, code_mode=True)
        code = 'r = await call_tool("get_task", {})\nr.title'
        async with runtime:
            result = await server.call_tool("execute", {"code": code})
        assert "solo" in _text(result)

    @pytest.mark.anyio
    async def test_nested_page_attribute_access(self, sandbox_app: a2kit.App) -> None:
        runtime = build(sandbox_app)
        server = build_mcp_server(runtime, code_mode=True)
        code = 'page = await call_tool("list_tasks", {})\n[t.title for t in page.items]'
        async with runtime:
            result = await server.call_tool("execute", {"code": code})
        text = _text(result)
        assert "a" in text
        assert "b" in text


class TestExecuteDerivationCache:
    """Design D2: the per-`execute` stub/registry derivation is cached per
    catalog — a second call against a stable catalog reuses it."""

    @pytest.mark.anyio
    async def test_stub_derivation_is_cached_across_calls(self, sandbox_app: a2kit.App, monkeypatch: pytest.MonkeyPatch) -> None:
        from a2kit.packages.codemode import transform as codemode_transform

        calls = {"n": 0}
        real = codemode_transform.generate_stubs

        def _spy(reachable: Any) -> Any:
            calls["n"] += 1
            return real(reachable)

        monkeypatch.setattr(codemode_transform, "generate_stubs", _spy)

        runtime = build(sandbox_app)
        server = build_mcp_server(runtime, code_mode=True)
        code = 'r = await call_tool("get_task", {})\nr.title'
        async with runtime:
            await server.call_tool("execute", {"code": code})
            await server.call_tool("execute", {"code": code})
        assert calls["n"] == 1
