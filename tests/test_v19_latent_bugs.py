"""v0.19 latent-bug fixes — tests.

Covers:

- Multi-ConnectionConfig Depends on a single tool raises at decoration time
  (was: silent first-wins pick downstream).
- Connection-key shape normalization through the OTel/log pipeline: a
  tuple-shaped ``connection=`` produces a canonical ``"a-b"`` attribute on
  the logging contextvar (was: passed through unchanged).
"""

from typing import Annotated, Any, NamedTuple

import pytest
import structlog
from structlog.testing import LogCapture

import a2kit
from a2kit.connections import ConnectionConfig
from a2kit.di import Depends


class _PED(NamedTuple):
    project: str
    env: str
    db: str


class _XY(NamedTuple):
    a: str
    b: str


class _ConnA(ConnectionConfig):
    pass


class _ConnB(ConnectionConfig):
    pass


async def _factory_a() -> _ConnA:
    return _ConnA(key=("a",))


async def _factory_b() -> _ConnB:
    return _ConnB(key=("b",))


def test_multi_connection_typed_deps_rejected_at_decoration() -> None:
    with pytest.raises(TypeError, match="at most one ConnectionConfig"):

        @a2kit.tool()
        async def two_conns(  # pragma: no cover — decoration must raise
            *,
            a: Annotated[_ConnA, Depends(_factory_a)],
            b: Annotated[_ConnB, Depends(_factory_b)],
        ) -> dict:
            return {"a": a, "b": b}


def test_single_connection_typed_dep_still_decorates() -> None:
    @a2kit.tool()
    async def one_conn(*, a: Annotated[_ConnA, Depends(_factory_a)]) -> dict:
        return {"a": a}

    # Sanity — wrapper exists and is async-callable.
    assert callable(one_conn)


@pytest.fixture
def log_output() -> LogCapture:
    capture = LogCapture()
    structlog.configure(processors=[structlog.contextvars.merge_contextvars, capture])
    yield capture
    structlog.reset_defaults()


async def test_tuple_connection_normalized_on_otel_attribute(log_output: LogCapture) -> None:
    """A tuple-shaped ``connection=`` flows through as a canonical tuple-key
    so the OTel/log attribute reads as a hyphen-joined string."""

    class _MultiKey(ConnectionConfig, key=_PED):
        pass

    captured: dict[str, Any] = {}

    async def _resolver(*, connection: Any) -> _MultiKey:
        captured["raw"] = connection
        return _MultiKey(key=("p", "e", "d"))

    @a2kit.tool()
    async def t(*, conn: Annotated[_MultiKey, Depends(_resolver)]) -> dict:
        log = a2kit.get_tool_logger("v19.test")
        log.info("hit")
        return {"k": conn.key}

    out = await t(connection=("p", "e", "d"))
    assert out == {"k": ("p", "e", "d")}
    # The raw forwarded shape stays whatever the caller passed (factory contract).
    assert captured["raw"] == ("p", "e", "d")
    # But the structlog binding sees the canonical hyphen-joined form.
    [event] = log_output.entries
    assert event["tool.connection"] == "p-e-d"


async def test_list_connection_normalized_on_otel_attribute(log_output: LogCapture) -> None:
    class _MK(ConnectionConfig, key=_XY):
        pass

    async def _resolver(*, connection: Any) -> _MK:  # noqa: ARG001
        return _MK(key=("x", "y"))

    @a2kit.tool()
    async def t(*, conn: Annotated[_MK, Depends(_resolver)]) -> dict:
        a2kit.get_tool_logger("v19.test").info("hit")
        return {}

    await t(connection=["x", "y"])
    [event] = log_output.entries
    assert event["tool.connection"] == "x-y"


async def test_tuple_connection_normalized_on_write_not_allowed_exception() -> None:
    """The second consumer of `STATE_CONNECTION_KEY` — the WriteNotAllowed
    exception raised by WriteEnforce — must also see the canonical tuple,
    not whatever raw shape the caller passed.
    """
    from a2kit.exceptions import WriteNotAllowed  # noqa: PLC0415

    class _RO(ConnectionConfig, key=_PED):
        read_only: bool = True

    async def _resolver(*, connection: Any) -> _RO:  # noqa: ARG001
        return _RO(key=("p", "e", "d"), read_only=True)

    @a2kit.tool(write=True)
    async def mutate(*, conn: Annotated[_RO, Depends(_resolver)]) -> dict:  # noqa: ARG001
        return {}

    with pytest.raises(WriteNotAllowed) as exc_info:
        await mutate(connection=("p", "e", "d"))
    # WriteNotAllowed.connection_key (positional arg) must be the canonical tuple.
    assert exc_info.value.connection_key == ("p", "e", "d")


async def test_runtime_multi_conn_guard_when_decoration_check_misses() -> None:
    """Authoritative runtime guard: factories whose return type isn't
    statically a ConnectionConfig (e.g. typed `Any` or a base class) but
    which return a ConnectionConfig instance at runtime must still fail.
    """

    class _A(ConnectionConfig, key=_XY):
        pass

    class _B(ConnectionConfig, key=_XY):
        pass

    async def _r_a(*, connection: Any) -> Any:  # noqa: ARG001
        return _A(key=("x", "y"))

    async def _r_b(*, connection: Any) -> Any:  # noqa: ARG001
        return _B(key=("x", "y"))

    @a2kit.tool()
    async def t(
        *,
        a: Annotated[Any, Depends(_r_a)],  # noqa: ARG001
        b: Annotated[Any, Depends(_r_b)],  # noqa: ARG001
    ) -> dict:
        return {}

    with pytest.raises(TypeError, match="more than one ConnectionConfig"):
        await t(connection=("x", "y"))
