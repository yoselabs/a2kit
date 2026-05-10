"""``a2kit.ToolContext`` is a lazy re-export of ``fastmcp.Context``.

These regressions guard the alias identity (Section 2.5) and ``import *``
binding (Section 2.6) of fastmcp-context-passthrough.
"""

from __future__ import annotations


def test_toolcontext_resolves_to_fastmcp_context() -> None:
    import a2kit
    from fastmcp import Context

    assert a2kit.ToolContext is Context, f"a2kit.ToolContext should re-export fastmcp.Context, got {a2kit.ToolContext!r}"


def test_import_star_binds_toolcontext() -> None:
    """``from a2kit import *`` must include ``ToolContext`` per ``__all__``."""
    import a2kit

    assert "ToolContext" in a2kit.__all__
    namespace: dict[str, object] = {}
    exec("from a2kit import *", namespace)  # noqa: S102 -- exercising the wildcard import path
    assert "ToolContext" in namespace
    from fastmcp import Context

    assert namespace["ToolContext"] is Context
