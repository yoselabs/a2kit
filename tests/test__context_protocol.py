"""BDD: `a2kit.ToolContext` is a Protocol satisfied by every transport's impl.

Scenarios:

- Identity: `a2kit.ToolContext` is the a2kit-owned Protocol, NOT
  `fastmcp.Context`.
- Structural conformance: both `fastmcp.Context` and `StderrToolContext`
  satisfy the Protocol via `isinstance`.
- Cold-start preserved: bare `import a2kit` does not load `fastmcp`.
"""

from __future__ import annotations

import subprocess
import sys
import typing

import a2kit


def test_a2kit_toolcontext_is_a_protocol() -> None:
    assert hasattr(a2kit.ToolContext, "_is_protocol")
    assert getattr(a2kit.ToolContext, "_is_protocol", False) is True
    # runtime_checkable Protocols expose _is_runtime_protocol
    assert getattr(a2kit.ToolContext, "_is_runtime_protocol", False) is True


def test_a2kit_toolcontext_is_not_fastmcp_context_identity() -> None:
    import fastmcp

    assert a2kit.ToolContext is not fastmcp.Context


def test_stderr_tool_context_satisfies_protocol() -> None:
    from a2kit.packages.context import StderrToolContext

    ctx = StderrToolContext()
    assert isinstance(ctx, a2kit.ToolContext)


def test_fastmcp_context_satisfies_protocol_class_level() -> None:
    """`fastmcp.Context` class structurally has the Protocol surface.

    We don't instantiate fastmcp.Context here (it needs a live request
    context); we assert the class-level surface contains every Protocol
    member.
    """
    import fastmcp

    proto_members = set(typing.get_type_hints(a2kit.ToolContext).keys()) | {
        "log",
        "debug",
        "info",
        "warning",
        "error",
        "report_progress",
        "set_state",
        "get_state",
        "delete_state",
    }
    for member in proto_members:
        assert hasattr(fastmcp.Context, member), f"fastmcp.Context missing {member!r}"


def test_cold_start_does_not_import_fastmcp() -> None:
    code = "import sys, a2kit; print('fastmcp' in sys.modules)"
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "False", f"`import a2kit` eagerly loaded fastmcp: {result.stdout!r}"
