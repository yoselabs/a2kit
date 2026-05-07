"""Tests for a2kit.docs — connection_param_doc canonical phrasing."""

from __future__ import annotations

from a2kit import docs


def test_default_phrasing() -> None:
    out = docs.connection_param_doc()
    assert "connection:" in out
    assert "a2kit connections list" in out
    assert "'prod'" in out


def test_custom_cli_and_example() -> None:
    out = docs.connection_param_doc(cli="a2widgets", example="prod")
    assert "a2widgets connections list" in out
    assert "'prod'" in out


def test_custom_param_name() -> None:
    out = docs.connection_param_doc(name="conn")
    assert out.startswith("conn:")


def test_custom_suffix() -> None:
    out = docs.connection_param_doc(custom_suffix="NOT a Jira project key.")
    assert out.endswith("NOT a Jira project key.")
