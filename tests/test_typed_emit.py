"""Round-4 Gap 1: typed-emit honors instance payloads.

Gherkin scenarios (mirroring `specs/mcp-context-passthrough/spec.md` modified
section "LDD event and report primitives are protocol-neutral functions"):

  Scenario: Kwargs form delivers an event
    GIVEN a tool calling event(ctx, "api.fetched", count=30)
    THEN the captured payload has name="api.fetched" and count=30

  Scenario: Typed form delivers an event by class
    GIVEN @dataclass ApiFetched(count: int) and event(ctx, ApiFetched(30))
    THEN the captured payload has name="ApiFetched" and count=30

  Scenario: Typed form with pydantic BaseModel
    GIVEN a BaseModel subclass and an instance
    THEN serialization goes through model_dump(mode="json")

  Scenario: Typed form with enum field
    GIVEN a dataclass with an Enum field
    THEN the enum value (not the enum instance) appears in the payload

  Scenario: Explicit name override on typed form
    GIVEN event(ctx, ApiFetched(30), name="api.custom_name")
    THEN the delivered name is "api.custom_name"

  Scenario: Legacy kwargs form is unaffected by name override path
    GIVEN event(ctx, "X", name="Y")
    THEN name="X" and payload={"name": "Y"} (legacy behavior preserved)
"""

from __future__ import annotations

import asyncio
import io
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel

from a2kit.ldd import event, ldd_state_for_call
from a2kit.packages.cli.context import StderrToolContext


def _run(coro: Any) -> str:
    """Run an emit-producing coroutine; return captured stderr."""
    buf = io.StringIO()
    saved = sys.stderr
    sys.stderr = buf
    try:
        asyncio.run(coro)
    finally:
        sys.stderr = saved
    return buf.getvalue()


def _kv(line: str) -> dict[str, str]:
    """Parse `k=val` pairs out of an LDD line."""
    pairs = re.findall(r"(\w+)=('[^']*'|\"[^\"]*\"|[^\s]+)", line)
    return {k: v.strip("'\"") for k, v in pairs}


# --- Kwargs form unchanged --- #


def test_kwargs_form_delivers_event() -> None:
    ctx = StderrToolContext()
    with ldd_state_for_call(tool_name="t"):
        out = _run(event(ctx, "api.fetched", count=30))
    assert "api.fetched" in out
    fields = _kv(out)
    assert fields["count"] == "30"


def test_kwargs_form_name_key_goes_into_payload() -> None:
    """Legacy: event(ctx, "X", name="Y") keeps name="X" and payload={"name": "Y"}."""
    ctx = StderrToolContext()
    with ldd_state_for_call(tool_name="t"):
        out = _run(event(ctx, "thing.happened", name="custom-id"))
    # The event name is "thing.happened" (appears in the msg slot before kv).
    assert "thing.happened" in out
    # The payload kv carries name='custom-id'.
    assert "name='custom-id'" in out or "name=custom-id" in out


# --- Typed form: dataclass --- #


@dataclass
class ApiFetched:
    count: int
    url: str


def test_dataclass_instance_emits_with_class_name() -> None:
    ctx = StderrToolContext()
    with ldd_state_for_call(tool_name="t"):
        out = _run(event(ctx, ApiFetched(count=30, url="https://x.test")))
    assert "ApiFetched" in out
    fields = _kv(out)
    assert fields["count"] == "30"
    # url repr-quoted by _format_kv since it's a string.
    assert "url='https://x.test'" in out


# --- Typed form: pydantic BaseModel --- #


class TierStarted(BaseModel):
    t_ms: int
    step: str
    when: datetime


def test_pydantic_basemodel_emits_via_model_dump() -> None:
    ctx = StderrToolContext()
    with ldd_state_for_call(tool_name="t"):
        out = _run(event(ctx, TierStarted(t_ms=42, step="raw", when=datetime(2026, 5, 11, 12, 0, tzinfo=UTC))))
    assert "TierStarted" in out
    fields = _kv(out)
    assert fields["t_ms"] == "42"
    # datetime is serialized via model_dump(mode="json") -> ISO string.
    assert "2026-05-11" in out


# --- Typed form: enum coercion --- #


class Verdict(Enum):
    OK = "ok"
    FAIL = "fail"


@dataclass
class TierEnded:
    step: str
    verdict: Verdict


def test_enum_field_coerced_to_value() -> None:
    ctx = StderrToolContext()
    with ldd_state_for_call(tool_name="t"):
        out = _run(event(ctx, TierEnded(step="raw", verdict=Verdict.OK)))
    # Should see 'ok' (the enum value), not 'Verdict.OK' (the enum repr).
    assert "verdict='ok'" in out
    assert "Verdict.OK" not in out


# --- Name override on typed form --- #


def test_name_override_on_instance_path() -> None:
    ctx = StderrToolContext()
    with ldd_state_for_call(tool_name="t"):
        out = _run(event(ctx, ApiFetched(count=1, url="u"), name="api.custom"))
    assert "api.custom" in out
    # The class name "ApiFetched" should NOT appear as the event name.
    # (It may appear elsewhere if msg cap leaks it, but we check the head.)
    first_line = out.splitlines()[0]
    assert "ApiFetched" not in first_line


# --- Mixing instance with extra payload kwargs --- #


def test_extra_kwargs_merged_into_instance_payload() -> None:
    ctx = StderrToolContext()
    with ldd_state_for_call(tool_name="t"):
        out = _run(event(ctx, ApiFetched(count=1, url="u"), extra_field="bonus"))
    assert "ApiFetched" in out
    assert "extra_field='bonus'" in out
    # Original instance fields preserved.
    fields = _kv(out)
    assert fields["count"] == "1"
