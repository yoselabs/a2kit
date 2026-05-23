"""``compile_selector`` parser + ``Selector.matches`` evaluator."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from a2kit.packages.select import Selector, SelectorError, compile_selector


@dataclass
class _FakeDesc:
    """Minimal stand-in for ``ToolDescriptor`` — just the fields selectors read."""

    name: str
    verb: str
    expose: tuple[str, ...] = ("mcp", "api")


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def test_compile_verb_include() -> None:
    s = compile_selector("verb=read,list")
    assert s.category == "verb"
    assert s.include == frozenset({"read", "list"})
    assert s.exclude == frozenset()


def test_compile_with_negation() -> None:
    s = compile_selector("name=fetch_*,!internal_*")
    assert s.include == frozenset({"fetch_*"})
    assert s.exclude == frozenset({"internal_*"})


def test_compile_exclude_only() -> None:
    s = compile_selector("name=!internal_*")
    assert s.include == frozenset()
    assert s.exclude == frozenset({"internal_*"})


def test_whitespace_stripped() -> None:
    s = compile_selector("verb = read , list ,! write")
    assert s.include == frozenset({"read", "list"})
    assert s.exclude == frozenset({"write"})


def test_missing_equals_raises() -> None:
    with pytest.raises(SelectorError, match="category=values"):
        compile_selector("verb read")


def test_unknown_category_raises() -> None:
    with pytest.raises(SelectorError, match="unknown category 'rooter'"):
        compile_selector("rooter=foo")


def test_empty_value_raises() -> None:
    with pytest.raises(SelectorError, match="empty value"):
        compile_selector("verb=")


def test_negation_only_with_no_value_raises() -> None:
    with pytest.raises(SelectorError, match="empty value"):
        compile_selector("verb=!")


def test_surface_value_outside_allowed_set_raises() -> None:
    with pytest.raises(SelectorError, match="surface accepts only"):
        compile_selector("surface=cli")


def test_reserved_char_inside_value_raises() -> None:
    # `!` only valid as a leading prefix on a value
    with pytest.raises(SelectorError, match="reserved char"):
        compile_selector("name=foo!bar")


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------


def test_verb_match_string_equality() -> None:
    s = compile_selector("verb=read,list")
    assert s.matches(_FakeDesc(name="x", verb="read"))
    assert s.matches(_FakeDesc(name="x", verb="list"))
    assert not s.matches(_FakeDesc(name="x", verb="write"))


def test_verb_negation_excludes() -> None:
    s = compile_selector("verb=!write")
    assert s.matches(_FakeDesc(name="x", verb="read"))
    assert not s.matches(_FakeDesc(name="x", verb="write"))


def test_name_fnmatch_case_sensitive() -> None:
    s = compile_selector("name=fetch_*")
    assert s.matches(_FakeDesc(name="fetch_user", verb="read"))
    assert not s.matches(_FakeDesc(name="Fetch_user", verb="read"))


def test_name_include_plus_exclude() -> None:
    s = compile_selector("name=fetch_*,!internal_*")
    assert s.matches(_FakeDesc(name="fetch_user", verb="read"))
    assert not s.matches(_FakeDesc(name="internal_fetch_diag", verb="read"))


def test_surface_membership_in_expose() -> None:
    s = compile_selector("surface=mcp")
    assert s.matches(_FakeDesc(name="t", verb="read", expose=("mcp", "api")))
    assert s.matches(_FakeDesc(name="t", verb="read", expose=("mcp",)))
    assert not s.matches(_FakeDesc(name="t", verb="read", expose=("api",)))


def test_empty_include_passes_vacuously() -> None:
    """Exclude-only selectors: every descriptor passes the include check."""
    s = compile_selector("name=!internal_*")
    # Non-empty exclude eliminates internal_; everything else passes.
    assert s.matches(_FakeDesc(name="public_x", verb="read"))


def test_selector_is_frozen() -> None:
    """Frozen dataclass: runtime attribute assignment raises FrozenInstanceError.

    ``setattr`` defers the check to runtime where ``frozen=True``
    semantics actually apply (a direct ``s.category =`` would also be
    caught statically by ``ty``).
    """
    s = compile_selector("verb=read")
    with pytest.raises(Exception):  # noqa: B017, PT011
        setattr(s, "category", "name")  # noqa: B010


# ---------------------------------------------------------------------------
# Integration with App.build(select=...)
# ---------------------------------------------------------------------------


import a2kit  # noqa: E402
from a2kit.runtime import build  # noqa: E402


def _build_three_tool_app() -> a2kit.App:
    class R(a2kit.Router):
        slug = "demo"

        @a2kit.read()
        async def fetch_user(self, *, k: str) -> dict[str, str]:
            return {"k": k}

        @a2kit.write()
        async def upsert_user(self, *, k: str) -> dict[str, str]:
            return {"k": k}

        @a2kit.read(expose=("mcp",))
        async def llm_only(self, *, k: str) -> dict[str, str]:
            return {"k": k}

        tools = (fetch_user, upsert_user, llm_only)

    return a2kit.App("demo").add_router(R())


def test_build_with_verb_select_filters_descriptors() -> None:
    runtime = build(_build_three_tool_app(), select=["verb=read"])
    names = {d.name for d in runtime.tools()}
    assert names == {"fetch_user", "llm_only"}


def test_build_with_surface_select_narrows_expose_and_drops_unmounted() -> None:
    """``surface=api`` drops ``llm_only`` (mcp-only) and clears mcp_surface."""
    runtime = build(_build_three_tool_app(), select=["surface=api"])
    names = {d.name for d in runtime.tools()}
    assert "llm_only" not in names
    # Surviving descriptors get expose narrowed to ('api',).
    for d in runtime.tools():
        assert d.expose == ("api",)
    # mcp_surface (never touched on this App) stays None; api_surface too
    # (never touched). Filter logic just ensures consistency.
    assert runtime.mcp_surface is None


def test_build_with_multiple_selects_ands() -> None:
    runtime = build(
        _build_three_tool_app(),
        select=["verb=read", "name=fetch_*"],
    )
    names = {d.name for d in runtime.tools()}
    assert names == {"fetch_user"}


def test_build_with_select_none_passes_through() -> None:
    runtime_a = build(_build_three_tool_app())
    runtime_b = build(_build_three_tool_app(), select=None)
    runtime_c = build(_build_three_tool_app(), select=[])
    assert len(runtime_a.tools()) == 3
    assert len(runtime_b.tools()) == 3
    assert len(runtime_c.tools()) == 3


def test_build_select_compile_error_raises_before_app_work() -> None:
    with pytest.raises(SelectorError, match="unknown category"):
        build(_build_three_tool_app(), select=["rooter=memories"])


def test_build_does_not_invoke_selector_on_dispatch_path() -> None:
    """Selectors are frozen at build; dispatch never reaches Selector.matches.

    Sentinel: patch ``Selector.matches`` to raise; if dispatch reached it,
    a call to the surviving tool would surface the error. It does not.
    """
    from unittest.mock import patch

    import asyncio

    from a2kit.packages.http import build_http_app
    from fastapi.testclient import TestClient

    runtime = build(_build_three_tool_app(), select=["verb=read"])

    async def _run() -> Any:
        async with runtime:
            api = build_http_app(runtime)
            with TestClient(api) as client, patch.object(Selector, "matches", side_effect=AssertionError("dispatch hit Selector.matches")):
                return client.post("/fetch_user", json={"k": "x"})

    r = asyncio.run(_run())
    assert r.status_code == 200
