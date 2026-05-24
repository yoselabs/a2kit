"""`DISPATCH_PIPELINE` ordering and the `fold_pipeline` helper."""

from __future__ import annotations

import asyncio
import functools
import inspect
from typing import Any

import a2kit
from a2kit.runtime import build
from a2kit.packages.dispatch import DISPATCH_PIPELINE, ToolBuildSpec, fold_pipeline


def test_dispatch_pipeline_order_lives_in_one_constant() -> None:
    assert [s.name for s in DISPATCH_PIPELINE] == [
        "timeout",
        "enricher",
        "router-lazy-enter",
        "dispatch-hook",
        "authorize-gate",
        "ldd-state",
        "error-capture",
    ]


def test_fold_applies_stages_innermost_first() -> None:
    calls: list[str] = []

    class _Recorder:
        def __init__(self, label: str) -> None:
            self.name = label

        def wrap(self, fn: Any, spec: ToolBuildSpec) -> Any:  # noqa: ARG002
            @functools.wraps(fn)
            async def _w(*a: Any, **k: Any) -> Any:
                calls.append(f"enter:{self.name}")
                result = fn(*a, **k)
                if inspect.isawaitable(result):
                    result = await result
                calls.append(f"exit:{self.name}")
                return result

            return _w

    async def _body() -> str:
        calls.append("body")
        return "done"

    spec = ToolBuildSpec(app=build(a2kit.App("fold-test")), router=None, meta=None)
    folded = fold_pipeline(_body, spec, (_Recorder("inner"), _Recorder("outer")))
    result = asyncio.run(folded())

    assert result == "done"
    # The last stage in the tuple ends up outermost.
    assert calls == ["enter:outer", "enter:inner", "body", "exit:inner", "exit:outer"]


def test_fold_drops_self_skipping_stages() -> None:
    """A stage that returns ``fn`` unchanged contributes no wrapper."""

    class _Skip:
        name = "skip"

        def wrap(self, fn: Any, spec: ToolBuildSpec) -> Any:  # noqa: ARG002
            return fn

    async def _body() -> str:
        return "done"

    spec = ToolBuildSpec(app=build(a2kit.App("fold-skip")), router=None, meta=None)
    folded = fold_pipeline(_body, spec, (_Skip(), _Skip()))
    assert folded is _body
