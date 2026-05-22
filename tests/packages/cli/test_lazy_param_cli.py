"""BDD: ``Lazy[T]`` skips resource entry under the CLI runtime."""

from __future__ import annotations

import pytest

import a2kit
from a2kit.metadata import get_meta
from a2kit.packages.cli.runtime import invoke_tool_sync
from a2kit.packages.di import Lazy
from a2kit.packages.dispatch import ToolBuildSpec


class _Browser:
    enter_count: int = 0
    exit_count: int = 0

    async def __aenter__(self) -> _Browser:
        type(self).enter_count += 1
        return self

    async def __aexit__(self, *exc: object) -> None:
        type(self).exit_count += 1


@pytest.fixture(autouse=True)
def _reset() -> None:
    _Browser.enter_count = 0
    _Browser.exit_count = 0


@a2kit.read()
async def _skip_browser(browser: Lazy[_Browser]) -> dict:
    return {"used": False}


def test_lazy_never_invoked_under_cli() -> None:
    """Body never awaits ``browser()`` → ``Browser.__aenter__`` never runs."""
    app = a2kit.App("lazy-cli")
    app.provide(_Browser)  # app-scope

    spec = ToolBuildSpec(app=app, router=None, meta=get_meta(_skip_browser))
    invoke_tool_sync(_skip_browser, {}, fmt="json", spec=spec)

    assert _Browser.enter_count == 0, f"Browser.__aenter__ ran {_Browser.enter_count} times despite Lazy not awaited"
    assert _Browser.exit_count == 0
