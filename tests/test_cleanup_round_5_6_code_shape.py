"""Tests — cleanup-round-5-6-code-shape bundle.

Covers items A (LDD ctx binding consistency), B (Container._override),
F (shorthand error fidelity is exercised in test_ambient_ldd_ctx.py),
and L (WARN_ONCE on docstring/get_type_hints failures).
"""

from __future__ import annotations

import asyncio
import logging
import pytest

import a2kit
from a2kit._docstring import _WARN_ONCE as _DOC_WARN_ONCE
from a2kit._docstring import extract_param_descriptions
from a2kit.exceptions import AmbientContextMissing
from a2kit.ldd import event as ldd_event
from a2kit.packages.di.container import Container
from a2kit.tool import _AUGMENT_WARN_ONCE, _augment_annotations_from_docstring


# --- A. LDD ctx binding consistency — CLI + TestClient must not synthesize --- #


class _NoCtxRouter(a2kit.Router):
    @a2kit.read()
    async def ping(self) -> dict[str, str]:
        await ldd_event("from-no-ctx-tool")
        return {"ok": "yes"}


def test_test_client_no_ctx_tool_raises_on_ldd_primitive() -> None:
    """TestClient must not synthesize a capturing ctx for a no-ctx tool."""
    from a2kit.testing import client

    app = a2kit.App("noctx").add_router(_NoCtxRouter())

    async def go() -> None:
        async with client(app) as c:
            with pytest.raises(AmbientContextMissing):
                await c.invoke("ping")

    asyncio.run(go())


def test_cli_runtime_no_ctx_tool_raises_on_ldd_primitive() -> None:
    """CLI runtime must not synthesize a StderrToolContext for a no-ctx tool."""
    from a2kit.packages.cli.runtime import invoke_tool_sync

    async def tool_body() -> dict[str, str]:
        await ldd_event("x")
        return {"ok": "yes"}

    with pytest.raises(AmbientContextMissing):
        invoke_tool_sync(tool_body, {}, ctx_param_name=None)


# --- B. Container._override --- #


class _Greeter:
    def __init__(self) -> None:
        self.name = "real"

    def hello(self) -> str:
        return f"hello from {self.name}"


def test_override_pins_singleton() -> None:
    c = Container()
    c.register_singleton(_Greeter, _Greeter)
    fake = _Greeter()
    fake.name = "fake"
    c._override(_Greeter, fake)
    assert c.resolve(_Greeter) is fake


def test_override_pins_per_call_provider() -> None:
    c = Container()
    c.register(_Greeter)
    fake = _Greeter()
    fake.name = "override"
    c._override(_Greeter, fake)
    assert c.resolve(_Greeter) is fake


def test_override_clears_async_factory_marker() -> None:
    c = Container()

    async def afactory() -> _Greeter:
        return _Greeter()

    c.register_singleton(_Greeter, afactory)
    assert c.has_async_singleton(_Greeter)
    fake = _Greeter()
    c._override(_Greeter, fake)
    assert not c.has_async_singleton(_Greeter)
    # Sync resolve no longer raises now that the marker is cleared.
    assert c.resolve(_Greeter) is fake


def test_override_then_restore_returns_to_pre_snapshot_state() -> None:
    c = Container()
    c.register(_Greeter)
    snapshot = c._snapshot()
    fake = _Greeter()
    fake.name = "fake"
    c._override(_Greeter, fake)
    assert c.resolve(_Greeter) is fake
    c._restore(snapshot)
    fresh = c.resolve(_Greeter)
    assert fresh is not fake
    assert fresh.name == "real"


# --- L. WARN_ONCE on docstring / get_type_hints failures --- #


def test_extract_warn_once_per_fn_name(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    """A function whose docstring blows up the parser emits one WARN per name."""
    _DOC_WARN_ONCE.discard("victim_tool")

    # Force _parse to raise so the except branch triggers deterministically.
    import a2kit._docstring as mod

    def _boom(_doc: str) -> dict[str, str]:
        raise RuntimeError("boom")

    monkeypatch.setattr(mod, "_parse", _boom)

    with caplog.at_level(logging.WARNING, logger="a2kit._docstring"):
        out1 = extract_param_descriptions("Args:\n    x: y.", fn_name="victim_tool")
        out2 = extract_param_descriptions("Args:\n    x: y.", fn_name="victim_tool")

    assert out1 == {}
    assert out2 == {}
    relevant = [r for r in caplog.records if "victim_tool" in r.getMessage()]
    assert len(relevant) == 1


def test_augment_warn_once_per_qualname(caplog: pytest.LogCaptureFixture) -> None:
    """A function with an unresolvable forward-ref annotation gets one WARN."""
    _AUGMENT_WARN_ONCE.discard("victim_tool_2")

    def victim_tool_2(x) -> None:  # noqa: ANN001
        """Do nothing.

        Args:
            x: a thing.
        """

    # Force get_type_hints to fail by injecting an unresolvable forward ref.
    victim_tool_2.__annotations__ = {"x": "DefinitelyNotAType"}
    victim_tool_2.__qualname__ = "victim_tool_2"

    with caplog.at_level(logging.WARNING, logger="a2kit.tool"):
        _augment_annotations_from_docstring(victim_tool_2)
        _augment_annotations_from_docstring(victim_tool_2)

    relevant = [r for r in caplog.records if r.name == "a2kit.tool" and "victim_tool_2" in r.getMessage()]
    assert len(relevant) == 1
