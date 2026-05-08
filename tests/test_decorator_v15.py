"""v0.15 surface tests for `@a2kit.tool` / `@a2kit.read` / `@a2kit.write` /
`@a2kit.list` and the underlying decorator behaviour.

These exercise only the v0.15 idiom (Annotated/Depends; no `connection_param=`,
no `*, info: ConnT` autodetect, no `store=` autoload).
"""

from typing import Annotated

import pytest

import a2kit
from a2kit import Local, Page, Passthrough
from a2kit.di import Depends


# ---------------------------------------------------------------------------- #
# tool() basic shape                                                            #
# ---------------------------------------------------------------------------- #


def test_tool_no_args_works() -> None:
    @a2kit.tool()
    def echo(x: int) -> dict:
        return {"x": x}

    assert echo(x=5) == {"x": 5}


def test_tool_rejects_str_return_at_decoration() -> None:
    def f(x: int) -> str:
        return str(x)

    with pytest.raises(a2kit.InvalidToolReturnTypeError):
        a2kit.tool()(f)


async def test_async_tool_basic() -> None:
    @a2kit.tool()
    async def aecho(x: int) -> dict:
        return {"x": x * 2}

    assert await aecho(x=3) == {"x": 6}


# ---------------------------------------------------------------------------- #
# Verb decorators add caps                                                      #
# ---------------------------------------------------------------------------- #


def test_read_verb_adds_read_cap() -> None:
    @a2kit.read()
    def get_one(*, id: str) -> dict:  # noqa: A002
        return {"id": id}

    caps = getattr(get_one, "_a2kit_capabilities", set())
    assert a2kit.Cap.READ in caps


def test_write_verb_adds_write_cap_and_default_write_true() -> None:
    @a2kit.write()
    def make_one(*, name: str) -> dict:
        return {"name": name}

    caps = getattr(make_one, "_a2kit_capabilities", set())
    assert a2kit.Cap.WRITE in caps


def test_list_verb_defaults_listview_local() -> None:
    @a2kit.list()
    def items() -> list[dict]:
        return [{"a": 1}, {"a": 2}]

    # Calling with limit should clamp to 1 row through the local listview kit;
    # the result wraps in a `Response` whose serialised data carries one row.
    out = items(limit=1)
    assert isinstance(out, a2kit.Response)
    # tsv shape: header + exactly one data row.
    assert out.data.count("\n") == 1


# ---------------------------------------------------------------------------- #
# Annotated/Depends path on @a2kit.tool                                         #
# ---------------------------------------------------------------------------- #


async def _make_value() -> dict:
    return {"made": "by-factory"}


async def test_tool_resolves_annotated_depends() -> None:
    @a2kit.tool()
    async def use_dep(*, val: Annotated[dict, Depends(_make_value)]) -> dict:
        return {"got": val}

    result = await use_dep()
    assert result == {"got": {"made": "by-factory"}}


def test_sync_tool_with_depends_raises() -> None:
    """Depends factories are async-resolution; a sync tool with one must error."""

    def make_str() -> str:
        return ""

    with pytest.raises(TypeError, match="async tool function"):

        @a2kit.tool()
        def synctool(*, x: Annotated[str, Depends(make_str)]) -> dict:  # noqa: ARG001
            return {}


# ---------------------------------------------------------------------------- #
# tool_call_guard                                                              #
# ---------------------------------------------------------------------------- #


async def test_tool_call_contamination_detected() -> None:
    @a2kit.tool()
    async def fmt(text: str) -> dict:
        return {"text": text}

    # Tool-call-style strings get rejected. Use the canonical tool-call shape.
    with pytest.raises(a2kit.ToolCallContamination):
        await fmt(text='<parameter name="x">1</parameter>')


async def test_tool_call_guard_can_be_disabled() -> None:
    @a2kit.tool(tool_call_guard=False)
    async def fmt(text: str) -> dict:
        return {"text": text}

    out = await fmt(text='<parameter name="x">1</parameter>')
    assert out == {"text": '<parameter name="x">1</parameter>'}


# ---------------------------------------------------------------------------- #
# Enricher                                                                      #
# ---------------------------------------------------------------------------- #


async def test_async_enricher_runs_on_exception() -> None:
    captured: dict = {}

    def my_enricher(exc: Exception, tool_name: str) -> Exception:
        captured["name"] = tool_name
        return ValueError(f"enriched: {exc}")

    @a2kit.tool(enricher=my_enricher)
    async def fail() -> dict:  # noqa: RUF029
        msg = "boom"
        raise RuntimeError(msg)

    with pytest.raises(ValueError, match="enriched: boom"):
        await fail()
    assert captured["name"] == "fail"


def test_sync_enricher_runs_on_exception() -> None:
    def my_enricher(exc: Exception, tool_name: str) -> Exception:  # noqa: ARG001
        return ValueError(f"enriched: {exc}")

    @a2kit.tool(enricher=my_enricher)
    def fail(x: int) -> dict:  # noqa: ARG001
        msg = "kaboom"
        raise RuntimeError(msg)

    with pytest.raises(ValueError, match="enriched: kaboom"):
        fail(x=1)


# ---------------------------------------------------------------------------- #
# Listview kit                                                                  #
# ---------------------------------------------------------------------------- #


def test_listview_local_filter() -> None:
    @a2kit.tool(filter=Local, fields=Local, pagination=Local)
    def items() -> list[dict]:
        return [{"a": 1, "b": 2}, {"a": 3, "b": 4}]

    # The kit wraps list-shaped output into a serialised Response when all
    # three listview concerns are Local-managed.
    out = items(limit=1)
    assert isinstance(out, a2kit.Response)
    # tsv data carries exactly one row past the header.
    assert out.data.count("\n") == 1


def test_passthrough_filter_requires_param() -> None:
    """A Passthrough listview mode requires a matching param on the function."""
    with pytest.raises(ValueError, match="Passthrough"):

        @a2kit.tool(filter=Passthrough)
        def bad() -> list[dict]:  # pragma: no cover
            return []


def test_page_generic_serialisation() -> None:
    """Page[T] is the standard wrapped result for paginated tools."""
    p = Page(items=[{"a": 1}], next_cursor=None)
    assert p.items == [{"a": 1}]
    assert p.next_cursor is None
