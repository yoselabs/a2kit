"""Tests for v0.2-only exception types: WriteNotAllowed, ToolCallContamination."""

from __future__ import annotations

import pytest

from a2kit import A2KitError, ToolCallContamination, WriteNotAllowed


def test_write_not_allowed_message() -> None:
    exc = WriteNotAllowed(("prod",), tool_name="update_widget")
    assert "prod" in str(exc)
    assert "update_widget" in str(exc)
    assert isinstance(exc, A2KitError)
    assert isinstance(exc, PermissionError)


def test_write_not_allowed_no_tool_name() -> None:
    exc = WriteNotAllowed(("a", "b"))
    assert "a-b" in str(exc)
    assert "tool '" not in str(exc)  # no tool-name-suffix


def test_write_not_allowed_empty_key() -> None:
    exc = WriteNotAllowed(())
    assert "<unknown>" in str(exc)


def test_tool_call_contamination_message() -> None:
    exc = ToolCallContamination("body", tool_name="t")
    assert "body" in str(exc)
    assert "t" in str(exc)
    assert isinstance(exc, ValueError)


def test_tool_call_contamination_no_tool_name() -> None:
    exc = ToolCallContamination("body")
    assert "body" in str(exc)


def test_can_raise_and_catch() -> None:
    with pytest.raises(A2KitError):
        raise WriteNotAllowed(("k",))
