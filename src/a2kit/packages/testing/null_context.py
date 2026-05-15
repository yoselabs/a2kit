"""Null ``ToolContext`` shim for unit-testing internal phase functions.

Round-4 a2web feedback (Soft B): consumers want a non-Optional ``ctx`` in
production code. The in-process ``a2kit.testing.client`` handles end-to-end
dispatcher tests, but internal phase functions are unit-tested without a full
App. Today every consumer ends up writing a no-op shim or carries
``ctx: ToolContext | None`` with ``if ctx is None`` guards at every emit site.

This shim is the single canonical no-op. Pass it where any function expects
``a2kit.ToolContext``::

    from a2kit.testing import null_context

    async def test_phase() -> None:
        ctx = null_context()
        await fetch_tier(ctx, url="https://x.test")

Logging, progress, event emission, state, and report calls are all silent
no-ops. The MCP-side surface (sample, list_resources, etc.) that the CLI
stub raises ``MCPOnlyError`` for is overridden to ``None`` here so unit tests
of code paths that touch them don't blow up.
"""

from __future__ import annotations

from typing import Any

from a2kit.packages.cli.context import StderrToolContext


class _NullToolContext(StderrToolContext):
    """No-op ``a2kit.ToolContext`` shim. All wire methods drop silently."""

    __slots__ = ()

    def __init__(self) -> None:
        super().__init__()
        # Fixed sentinel exposed via ``ctx.request_id`` — useful for log assertions.
        self.request_id = "null-context"

    def _emit(
        self,
        level: str,  # noqa: ARG002
        msg: str,  # noqa: ARG002
        fields: Any,  # noqa: ARG002
        *,
        elapsed_ms: int | None = None,  # noqa: ARG002
    ) -> None:
        # Drop silently. Logging, report_progress, event/report wire emit
        # all funnel through here; null context wants zero side effects.
        return

    # --- MCP-only surface overrides ---------------------------------------- #
    #
    # CLI stub raises MCPOnlyError on these. The null shim returns None so
    # unit tests of code paths that touch them don't blow up.

    async def sample(self, *args: Any, **kwargs: Any) -> Any:  # noqa: ARG002
        return None

    async def sample_step(self, *args: Any, **kwargs: Any) -> Any:  # noqa: ARG002
        return None

    async def list_resources(self) -> Any:
        return []

    async def list_prompts(self) -> Any:
        return []

    async def get_prompt(self, name: str, arguments: Any = None) -> Any:  # noqa: ARG002
        return None

    async def list_roots(self) -> Any:
        return []

    async def send_notification(self, notification: Any) -> None:  # noqa: ARG002
        return None

    async def read_resource(self, uri: str) -> Any:  # noqa: ARG002
        return ""

    async def elicit(
        self,
        message: str,  # noqa: ARG002
        response_type: Any = None,  # noqa: ARG002
        *,
        response_title: str | None = None,  # noqa: ARG002
        response_description: str | None = None,  # noqa: ARG002
    ) -> Any:
        return None


def null_context() -> Any:
    """Return a new no-op ``ToolContext``-shaped shim.

    Pass to functions annotated ``ctx: a2kit.ToolContext`` in unit tests that
    bypass :func:`a2kit.testing.client`. Every wire method (logging, progress,
    event, report, sample, etc.) is a silent no-op.
    """
    return _NullToolContext()


__all__ = ["null_context"]
