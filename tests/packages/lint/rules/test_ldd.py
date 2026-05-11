"""A2K-LDD-REPORT-TYPE — declaration discipline for ctx.report(...) calls."""

from __future__ import annotations

import ast
from textwrap import dedent

from a2kit.packages.lint.rules.ldd import rule_ldd_report_type
from a2kit.packages.lint.static import A2K_LDD_REPORT_TYPE


def _findings(src: str) -> list:
    tree = ast.parse(dedent(src))
    return list(rule_ldd_report_type(tree, "<test>", src))


def test_fires_when_ctx_report_called_without_reports_decorator() -> None:
    src = """
    import a2kit

    @a2kit.read()
    async def get_thing(*, ctx) -> dict:
        await ctx.report(thing=1)
        return {}
    """
    out = _findings(src)
    assert len(out) == 1
    assert out[0].rule == A2K_LDD_REPORT_TYPE


def test_silent_when_reports_decorator_present_and_module_scope() -> None:
    src = """
    from pydantic import BaseModel
    import a2kit
    from a2kit.packages.mcp.reports import reports

    class BatchReport(BaseModel):
        n: int

    @a2kit.read()
    @reports(BatchReport)
    async def get_thing(*, ctx) -> dict:
        await ctx.report(BatchReport(n=1))
        return {}
    """
    assert _findings(src) == []


def test_fires_when_reportt_is_not_module_scope() -> None:
    src = """
    from pydantic import BaseModel
    import a2kit
    from a2kit.packages.mcp.reports import reports

    def make_decorator():
        class InnerReport(BaseModel):
            n: int

        @a2kit.read()
        @reports(InnerReport)
        async def get_thing(*, ctx) -> dict:
            return {}
        return get_thing
    """
    out = _findings(src)
    assert any(f.rule == A2K_LDD_REPORT_TYPE for f in out)


def test_silent_for_tools_without_ctx_report_calls() -> None:
    src = """
    import a2kit

    @a2kit.read()
    async def plain(*, ctx) -> dict:
        ctx.info("hi")
        return {}
    """
    assert _findings(src) == []


def test_fires_for_each_call_site() -> None:
    src = """
    import a2kit

    @a2kit.list_()
    async def list_things(*, ctx) -> list:
        await ctx.report(a=1)
        await ctx.report(a=2)
        return []
    """
    out = _findings(src)
    assert len(out) == 2


def test_other_dot_report_not_flagged_when_no_decorator() -> None:
    """Plain ``foo.report(...)`` outside a tool body must not fire."""
    src = """
    def helper():
        x.report({"any": "thing"})
    """
    assert _findings(src) == []


def test_a2kit_tool_decorator_also_covered() -> None:
    src = """
    import a2kit

    @a2kit.tool()
    async def t(*, ctx) -> dict:
        await ctx.report(a=1)
        return {}
    """
    out = _findings(src)
    assert len(out) == 1
