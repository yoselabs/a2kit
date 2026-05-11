"""Tests for tool-return-type-discipline:

- Section 2: A2K-LOCAL-RETURN-MODEL lint rule (positive + negative)
- Section 3: decoration-time runtime check via _check_return_scope
- Section 4: a2kit.testing.peek

NOTE: this file deliberately does NOT use ``from __future__ import annotations``.
The decoration-time check inspects ``fn.__annotations__`` directly; if
annotations are stringified (PEP 563) the runtime check cannot resolve
function-local names without a ``locals`` dict (that's the whole failure mode
we're flagging). Tests for the *lint rule* don't depend on runtime evaluation
and work either way.
"""

import ast

import pytest
from pydantic import BaseModel

import a2kit
from a2kit.exceptions import InvalidToolReturnTypeError
from a2kit.packages.di.container import UnresolvableType
from a2kit.packages.lint.rules.local_return_model import rule_local_return_model
from a2kit.packages.lint.static import A2K_LOCAL_RETURN_MODEL
from a2kit.testing import peek


# Module-scope BaseModel for "passes" cases
class GoodResult(BaseModel):
    ok: bool


# ----- Lint rule tests --------------------------------------------------- #


def _lint(source: str, filename: str = "x.py") -> list:
    tree = ast.parse(source)
    return list(rule_local_return_model(tree, filename, source))


def test_in_function_basemodel_direct_return_fires() -> None:
    src = """\
import a2kit
from pydantic import BaseModel

def make_router():
    class Result(BaseModel):
        ok: bool
    class R(a2kit.Router):
        @a2kit.read()
        async def t(self) -> Result:
            return Result(ok=True)
"""
    msgs = _lint(src)
    assert len(msgs) == 1
    assert msgs[0].rule == A2K_LOCAL_RETURN_MODEL
    assert "Result" in msgs[0].message


def test_in_function_basemodel_via_generic_carrier_fires() -> None:
    src = """\
import a2kit
from pydantic import BaseModel

def make_router():
    class Item(BaseModel):
        n: int
    class R(a2kit.Router):
        @a2kit.read()
        async def t(self) -> list[Item]:
            return []
"""
    msgs = _lint(src)
    assert len(msgs) == 1
    assert "Item" in msgs[0].message


def test_module_scope_basemodel_passes() -> None:
    src = """\
import a2kit
from pydantic import BaseModel

class Result(BaseModel):
    ok: bool

class R(a2kit.Router):
    @a2kit.read()
    async def t(self) -> Result:
        return Result(ok=True)
"""
    assert _lint(src) == []


def test_imported_basemodel_passes() -> None:
    src = """\
import a2kit
from othermod import OtherResult

class R(a2kit.Router):
    @a2kit.read()
    async def t(self) -> OtherResult:
        return OtherResult()
"""
    assert _lint(src) == []


def test_type_checking_block_exempt() -> None:
    src = """\
import a2kit
from pydantic import BaseModel
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    class Result(BaseModel):
        ok: bool

class R(a2kit.Router):
    @a2kit.read()
    async def t(self) -> "Result":
        ...
"""
    # The annotation is a string forward-ref; either way, the class inside
    # TYPE_CHECKING is not in the nested set, so no fire.
    assert _lint(src) == []


def test_multiple_tool_violations_each_fire_at_correct_lineno() -> None:
    src = """\
import a2kit
from pydantic import BaseModel

def make():
    class Inner1(BaseModel):
        a: int
    class Inner2(BaseModel):
        b: int
    class R(a2kit.Router):
        @a2kit.read()
        async def t1(self) -> Inner1: ...
        @a2kit.read()
        async def t2(self) -> Inner2: ...
"""
    msgs = _lint(src)
    assert len(msgs) == 2
    # Both fire on the annotation site, distinct lines.
    lines = sorted(m.line for m in msgs)
    assert lines[0] != lines[1]


def test_pep604_union_with_local_basemodel_fires() -> None:
    src = """\
import a2kit
from pydantic import BaseModel

def make():
    class L(BaseModel):
        ok: bool
    class R(a2kit.Router):
        @a2kit.read()
        async def t(self) -> L | None:
            return None
"""
    msgs = _lint(src)
    assert len(msgs) == 1
    assert "L" in msgs[0].message


def test_non_basemodel_local_class_does_not_fire() -> None:
    src = """\
import a2kit

def make():
    class Result:  # plain class, NOT a BaseModel
        pass
    class R(a2kit.Router):
        @a2kit.read()
        async def t(self) -> Result:
            ...
"""
    # Rule scope is BaseModel subclasses only.
    assert _lint(src) == []


# ----- Decoration-time runtime check ------------------------------------ #


def _build_in_function_basemodel_router() -> None:
    """Helper that defines an in-function BaseModel and a tool returning it.

    The ``noqa`` is intentional — this is the failure mode under test.
    """

    class LocalResult(BaseModel):
        ok: bool

    class R(a2kit.Router):
        @a2kit.read()
        async def t(self) -> LocalResult:  # noqa: A2K-LOCAL-RETURN-MODEL
            return LocalResult(ok=True)


def test_decoration_raises_for_in_function_basemodel() -> None:
    """Defining a tool whose return type is an in-function BaseModel raises at import time."""
    with pytest.raises(InvalidToolReturnTypeError) as ei:
        _build_in_function_basemodel_router()
    assert "A2K-LOCAL-RETURN-MODEL" in str(ei.value)
    assert "<locals>" in str(ei.value) or "non-module scope" in str(ei.value)


def test_decoration_passes_for_module_scope_basemodel() -> None:
    """Sanity: module-scope class still works."""

    class R(a2kit.Router):
        @a2kit.read()
        async def t(self) -> GoodResult:
            return GoodResult(ok=True)

    # No exception means pass; quick assertion to use the symbol
    assert R is not None


def _build_generic_carrier_router() -> None:
    class Inner(BaseModel):
        n: int

    class R(a2kit.Router):
        @a2kit.read()
        async def t(self) -> list[Inner]:  # noqa: A2K-LOCAL-RETURN-MODEL
            return []


def test_decoration_raises_for_generic_carrier_with_local_basemodel() -> None:
    with pytest.raises(InvalidToolReturnTypeError) as ei:
        _build_generic_carrier_router()
    assert "A2K-LOCAL-RETURN-MODEL" in str(ei.value)


def test_str_return_still_raises_existing_error() -> None:
    """Antipattern #1 enforcement is preserved (existing behavior)."""
    with pytest.raises(InvalidToolReturnTypeError) as ei:

        class R(a2kit.Router):
            @a2kit.read()
            async def t(self) -> str:
                return "hi"

    assert "antipattern #1" in str(ei.value) or "str" in str(ei.value)


@pytest.mark.parametrize(
    ("return_type", "type_name"),
    [
        (int, "int"),
        (float, "float"),
        (bool, "bool"),
        (bytes, "bytes"),
    ],
)
def test_primitive_returns_raise_invalid_tool_return_type(return_type: type, type_name: str) -> None:
    """Antipattern #1 broadened — all primitives + None rejected at decoration time."""

    # Build an async fn whose return annotation is the primitive type.
    async def fn() -> return_type:  # type: ignore[valid-type]
        return None  # type: ignore[return-value]

    fn.__annotations__["return"] = return_type

    with pytest.raises(InvalidToolReturnTypeError) as ei:
        a2kit.read()(fn)
    msg = str(ei.value)
    assert type_name in msg
    assert "antipattern #1" in msg
    assert "Pydantic model" in msg


def test_none_return_raises() -> None:
    """``-> None`` is also a primitive return — rejected with NoneType in the message."""

    async def fn() -> None:
        return None

    with pytest.raises(InvalidToolReturnTypeError) as ei:
        a2kit.read()(fn)
    assert "NoneType" in str(ei.value)


def test_decoration_passes_for_dict_return() -> None:
    """Dict returns aren't BaseModel subclasses, so the new check is a no-op."""

    class R(a2kit.Router):
        @a2kit.read()
        async def t(self) -> dict:
            return {"ok": True}

    assert R is not None


# ----- a2kit.testing.peek ------------------------------------------------- #


class _State:
    pass


def test_peek_resolves_registered_singleton() -> None:
    app = a2kit.App("t")
    app.singleton(_State, lambda: _State())
    s = peek(app, _State)
    assert isinstance(s, _State)
    s2 = peek(app, _State)
    assert s is s2  # singleton


def test_singleton_rejects_async_factory_at_registration() -> None:
    """v0.27: singleton factories MUST be sync. Async resource opens belong in
    resource classes (lazy-init pattern), not in DI factories."""

    async def factory() -> _State:
        return _State()

    app = a2kit.App("t")
    with pytest.raises(ValueError, match="async"):
        app.singleton(_State, factory)


def test_peek_raises_when_no_provider() -> None:
    """Peek on an App with no provider for the type gives an UnresolvableType."""
    app = a2kit.App("t")
    with pytest.raises(UnresolvableType):
        peek(app, _State)
