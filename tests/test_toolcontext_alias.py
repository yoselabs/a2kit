"""``a2kit.ToolContext`` is an a2kit-owned Protocol satisfied by every transport.

Identity changed in context-as-protocol (post-v0.38): previously a lazy
re-export of ``fastmcp.Context``, now the canonical Protocol declared in
``a2kit._context_protocol``. Wildcard binding still ships per ``__all__``.
Structural conformance lives in ``test_context_protocol.py``.
"""

from __future__ import annotations


def test_toolcontext_resolves_to_protocol() -> None:
    import a2kit
    from a2kit._context_protocol import ToolContext as ProtocolToolContext

    assert a2kit.ToolContext is ProtocolToolContext


def test_toolcontext_is_not_fastmcp_context() -> None:
    import a2kit
    from fastmcp import Context

    assert a2kit.ToolContext is not Context


def test_import_star_binds_toolcontext() -> None:
    """``from a2kit import *`` must include ``ToolContext`` per ``__all__``."""
    import a2kit
    from a2kit._context_protocol import ToolContext as ProtocolToolContext

    assert "ToolContext" in a2kit.__all__
    namespace: dict[str, object] = {}
    exec("from a2kit import *", namespace)  # noqa: S102 -- exercising the wildcard import path
    assert "ToolContext" in namespace
    assert namespace["ToolContext"] is ProtocolToolContext
