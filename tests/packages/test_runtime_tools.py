"""Mirror test for ``a2kit.packages.runtime_tools`` — pure resolver helpers.

End-to-end integration coverage (MCP + CLI surfaces) lives in
``tests/capabilities/runtime_tool_selection/``. This file mirrors the
source module per ``A2K-TEST-MIRROR`` and covers the public helpers
directly.
"""

from __future__ import annotations

import pytest

from a2kit.packages.runtime_tools import (
    ENV_VAR,
    ToolSelectionError,
    parse_selector,
    resolve_selector,
    validate_selector,
)


def test_env_var_name_is_a2kit_tools() -> None:
    assert ENV_VAR == "A2KIT_TOOLS"


def test_parse_selector_none_and_empty() -> None:
    assert parse_selector(None) is None
    assert parse_selector("") is None
    assert parse_selector(",,") is None


def test_parse_selector_single_and_list() -> None:
    assert parse_selector("ask") == frozenset({"ask"})
    assert parse_selector("ask,refresh") == frozenset({"ask", "refresh"})


def test_resolve_selector_env_only() -> None:
    assert resolve_selector(env="ask,refresh", cli_arg=None) == frozenset({"ask", "refresh"})


def test_resolve_selector_cli_only() -> None:
    assert resolve_selector(env="", cli_arg="ask") == frozenset({"ask"})


def test_resolve_selector_intersection() -> None:
    assert resolve_selector(env="ask,refresh", cli_arg="ask,fetch_raw") == frozenset({"ask"})


def test_resolve_selector_none_when_both_empty() -> None:
    assert resolve_selector(env="", cli_arg=None) is None


def test_validate_selector_pass() -> None:
    validate_selector(frozenset({"ask"}), available=["ask", "refresh"])


def test_validate_selector_unknown_raises() -> None:
    with pytest.raises(ToolSelectionError, match="bogus"):
        validate_selector(frozenset({"bogus"}), available=["ask"])
