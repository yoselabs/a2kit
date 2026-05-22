"""Integration: both transports fold the one shared `DISPATCH_PIPELINE`."""

from __future__ import annotations

import subprocess
import sys

import a2kit
from a2kit.metadata import get_meta
from a2kit.packages.cli.runtime import invoke_tool_sync
from a2kit.packages.dispatch import ToolBuildSpec


def test_cli_invocation_path_imports_no_fastmcp() -> None:
    """The CLI dispatch path (runtime + builder) must not pull fastmcp.

    The shared pipeline is fastmcp-free precisely so the CLI consumer can
    fold it without paying the cold-start cost.
    """
    code = "import sys\nimport a2kit.packages.cli.runtime\nimport a2kit.packages.cli.builder\nprint('fastmcp' in sys.modules)"
    out = subprocess.run(  # noqa: S603
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True,
    )
    assert out.stdout.strip() == "False", "fastmcp leaked into the CLI dispatch path"


def test_cli_adapter_enters_lifecycle_router_on_dispatch() -> None:
    """`RouterLazyEnterStage` closes the CLI parity gap.

    A router carrying ``__aenter__`` now enters on first CLI dispatch —
    before this change the CLI path had no router-lazy-enter wrapper at
    all, so lifecycle routers silently never entered.
    """

    class _Lifecycle(a2kit.Router):
        slug = "lc"

        def __init__(self) -> None:
            super().__init__()
            self.entered = False

        async def __aenter__(self) -> _Lifecycle:
            self.entered = True
            return self

        async def __aexit__(self, *exc: object) -> None:
            return None

        @a2kit.read()
        async def ping(self) -> dict:
            return {"ok": True}

        tools = (ping,)

    router = _Lifecycle()
    app = a2kit.App("cli-lifecycle").add_router(router)
    desc = app.tools()[0]
    spec = ToolBuildSpec(app=app, router=app.routers()[0], meta=get_meta(desc.fn))

    invoke_tool_sync(desc.fn, {}, fmt="json", spec=spec)
    assert router.entered is True


def test_no_legacy_wrap_functions_remain() -> None:
    """No `_wrap_with_*` dispatch wrapper survives in the transport adapters.

    Every transport-neutral dispatch concern lives once in
    ``a2kit.packages.dispatch``; neither adapter carries its own copy.
    """
    from a2kit.packages.cli import builder, runtime
    from a2kit.packages.mcp import _wrappers

    for mod in (_wrappers, builder, runtime):
        leftover = [n for n in dir(mod) if n.startswith("_wrap_with_")]
        assert not leftover, f"{mod.__name__} still defines {leftover}"
