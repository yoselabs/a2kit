"""`ToolBuildSpec`, the `DispatchStage` protocol, `CapturedError`, `has_injectables`."""

from __future__ import annotations

import dataclasses

import pytest

from a2kit.runtime import build
from a2kit.testing import app_of
from a2kit.packages.dispatch import (
    CapturedError,
    DispatchStage,
    TimeoutStage,
    ToolBuildSpec,
    has_injectables,
)


def test_tool_build_spec_is_a_frozen_dataclass() -> None:
    spec = ToolBuildSpec(app=build(app_of("spec-test")), router=None, meta=None)
    assert dataclasses.is_dataclass(spec)
    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.router = None  # type: ignore[misc]  # ty: ignore[invalid-assignment]


def test_captured_error_snapshots_the_original() -> None:
    try:
        raise ValueError("boom")
    except ValueError as exc:
        captured = CapturedError(exc)
        original = exc
    assert captured.original is original
    assert captured.class_name == "ValueError"
    assert captured.message == "boom"
    assert "ValueError" in captured.traceback_str
    assert "boom" in captured.traceback_str


def test_has_injectables_false_without_container() -> None:
    async def _fn() -> dict:
        return {}

    assert has_injectables(_fn, None) is False


def test_dispatch_stage_is_runtime_checkable() -> None:
    assert isinstance(TimeoutStage(), DispatchStage)

    class _NotAStage:
        pass

    assert not isinstance(_NotAStage(), DispatchStage)
