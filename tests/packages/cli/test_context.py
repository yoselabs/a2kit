"""`a2kit.packages.cli.context` is a tombstone.

The tool-context implementations (`StderrToolContext`, `MCPOnlyError`)
moved to the transport-neutral `a2kit.packages.context` package in the
import-acyclicity refactor. This mirror test locks the migration hint so
the old import path keeps failing loudly with a pointer at the new home.
The behavioural suite for the class lives in
`tests/packages/context/test_context.py`.
"""

from __future__ import annotations

import pytest


def test_stderr_tool_context_moved() -> None:
    import a2kit.packages.cli.context as cli_context

    with pytest.raises(ImportError, match=r"a2kit\.packages\.context"):
        _ = cli_context.StderrToolContext


def test_mcp_only_error_moved() -> None:
    import a2kit.packages.cli.context as cli_context

    with pytest.raises(ImportError, match=r"a2kit\.packages\.context"):
        _ = cli_context.MCPOnlyError
