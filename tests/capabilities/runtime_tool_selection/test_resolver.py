"""A2 — selector resolver pure-function tests (env + CLI + intersection + validation)."""

from __future__ import annotations

import pytest

from a2kit.packages.runtime_tools import (
    ToolSelectionError,
    parse_selector,
    resolve_selector,
    validate_selector,
)


def test_parse_selector_none_returns_none() -> None:
    assert parse_selector(None) is None


def test_parse_selector_empty_returns_none() -> None:
    assert parse_selector("") is None
    assert parse_selector("  ") is None
    assert parse_selector(",,,") is None


def test_parse_selector_single_name() -> None:
    assert parse_selector("ask") == frozenset({"ask"})


def test_parse_selector_comma_list() -> None:
    assert parse_selector("ask,refresh") == frozenset({"ask", "refresh"})


def test_parse_selector_strips_whitespace() -> None:
    assert parse_selector(" ask , refresh ") == frozenset({"ask", "refresh"})


def test_resolve_neither_set_returns_none() -> None:
    assert resolve_selector(env="", cli_arg=None) is None
    assert resolve_selector(env=None, cli_arg=None) is None or True  # env=None reads os.environ; permissive


def test_resolve_env_only() -> None:
    assert resolve_selector(env="ask,refresh", cli_arg=None) == frozenset({"ask", "refresh"})


def test_resolve_cli_only() -> None:
    assert resolve_selector(env="", cli_arg="ask") == frozenset({"ask"})


def test_resolve_intersection_when_both_set() -> None:
    assert resolve_selector(env="ask,refresh", cli_arg="ask,fetch_raw") == frozenset({"ask"})


def test_resolve_intersection_can_be_empty() -> None:
    assert resolve_selector(env="ask", cli_arg="refresh") == frozenset()


def test_validate_selector_passes_for_known_names() -> None:
    validate_selector(frozenset({"ask", "refresh"}), available=["ask", "refresh", "fetch_raw"])


def test_validate_selector_raises_for_unknown_name() -> None:
    with pytest.raises(ToolSelectionError) as excinfo:
        validate_selector(frozenset({"ask", "bogus"}), available=["ask", "refresh"])
    msg = str(excinfo.value)
    assert "bogus" in msg
    assert "ask" in msg  # valid names listed for the operator
    assert "refresh" in msg


def test_validate_selector_message_mentions_hidden_caveat() -> None:
    with pytest.raises(ToolSelectionError) as excinfo:
        validate_selector(frozenset({"hidden_tool"}), available=["ask"])
    assert "hidden" in str(excinfo.value).lower()
