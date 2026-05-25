"""BDD scenarios for A2K-RAISES-NOT-TYPED."""

import ast
import textwrap
from pathlib import Path

from a2effect._lint import raises_not_typed_rule


def _run(src: str) -> list:
    tree = ast.parse(textwrap.dedent(src))
    return list(raises_not_typed_rule(tree, path=Path("test.py"), source=src))


def test_raises_with_raw_asyncpg_type_fires_error() -> None:
    msgs = _run("""
        from typing import Annotated
        from a2effect import Raises
        import asyncpg

        async def fetch() -> Annotated[str, Raises(asyncpg.PostgresError)]:
            return "ok"
    """)
    assert len(msgs) == 1
    assert msgs[0].rule_id == "A2K-RAISES-NOT-TYPED"
    assert msgs[0].severity == "error"
    assert "asyncpg.PostgresError" in msgs[0].message


def test_raises_with_httpx_type_fires() -> None:
    msgs = _run("""
        from typing import Annotated
        from a2effect import Raises
        import httpx

        async def fetch() -> Annotated[str, Raises(httpx.HTTPStatusError)]:
            return "ok"
    """)
    assert any(m.rule_id == "A2K-RAISES-NOT-TYPED" for m in msgs)


def test_raises_with_local_app_error_does_not_fire() -> None:
    msgs = _run("""
        from typing import Annotated
        from a2effect import AppError, Raises

        class NotFound(AppError):
            kind = "input"

        async def fetch() -> Annotated[str, Raises(NotFound)]:
            return "ok"
    """)
    assert msgs == []


def test_raises_inside_param_annotation_also_inspected() -> None:
    msgs = _run("""
        from typing import Annotated
        from a2effect import Raises
        import asyncpg

        async def fetch(x: Annotated[str, Raises(asyncpg.PostgresError)]) -> str:
            return x
    """)
    assert any(m.rule_id == "A2K-RAISES-NOT-TYPED" for m in msgs)
