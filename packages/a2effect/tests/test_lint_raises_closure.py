"""BDD scenarios for A2K-RAISES-CLOSURE."""

import ast
import textwrap
from pathlib import Path

from a2effect._lint import raises_closure_rule


def _run(src: str) -> list:
    tree = ast.parse(textwrap.dedent(src))
    return list(raises_closure_rule(tree, path=Path("test.py"), source=src))


def test_undeclared_raise_emits_error() -> None:
    msgs = _run("""
        from typing import Annotated
        from a2effect import AppError, Raises
        import memory

        class NotFound(AppError):
            kind = "input"
        class InvalidId(AppError):
            kind = "input"

        @memory.read
        async def fetch(id: str) -> Annotated[str, Raises(NotFound)]:
            raise InvalidId("x")
    """)
    assert len(msgs) == 1
    assert msgs[0].rule_id == "A2K-RAISES-CLOSURE"
    assert msgs[0].severity == "error"
    assert "InvalidId" in msgs[0].message
    assert "NotFound" in msgs[0].message


def test_declared_raise_does_not_fire() -> None:
    msgs = _run("""
        from typing import Annotated
        from a2effect import AppError, Raises
        import memory

        class NotFound(AppError):
            kind = "input"

        @memory.read
        async def fetch(id: str) -> Annotated[str, Raises(NotFound)]:
            raise NotFound("x")
    """)
    assert msgs == []


def test_caught_and_translated_raise_does_not_fire() -> None:
    msgs = _run("""
        from typing import Annotated
        from a2effect import AppError, Raises
        import memory
        import asyncpg

        class InfrastructureError(AppError):
            kind = "infra"

        @memory.read
        async def fetch(id: str) -> Annotated[str, Raises(InfrastructureError)]:
            try:
                return await db.get(id)
            except asyncpg.PostgresError as e:
                raise InfrastructureError(str(e)) from e
    """)
    assert msgs == []


def test_function_without_raises_annotation_is_not_inspected() -> None:
    msgs = _run("""
        from typing import Annotated
        from a2effect import AppError
        import memory

        class InvalidId(AppError):
            kind = "input"

        @memory.read
        async def fetch(id: str) -> str:
            raise InvalidId("x")
    """)
    assert msgs == []


def test_non_tool_function_is_not_inspected() -> None:
    msgs = _run("""
        from typing import Annotated
        from a2effect import AppError, Raises

        class NotFound(AppError):
            kind = "input"
        class InvalidId(AppError):
            kind = "input"

        async def fetch(id: str) -> Annotated[str, Raises(NotFound)]:
            raise InvalidId("x")
    """)
    assert msgs == []


def test_bare_reraise_does_not_fire() -> None:
    msgs = _run("""
        from typing import Annotated
        from a2effect import AppError, Raises
        import memory

        class NotFound(AppError):
            kind = "input"

        @memory.read
        async def fetch(id: str) -> Annotated[str, Raises(NotFound)]:
            try:
                return "ok"
            except Exception:
                raise
    """)
    assert msgs == []
