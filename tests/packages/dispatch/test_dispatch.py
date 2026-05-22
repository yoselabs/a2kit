"""`a2kit.packages.dispatch` package surface — re-exports and the fastmcp-free invariant."""

from __future__ import annotations

import subprocess
import sys

from a2kit.packages import dispatch


def test_package_reexports_the_public_surface() -> None:
    for name in (
        "DISPATCH_PIPELINE",
        "DispatchStage",
        "ToolBuildSpec",
        "CapturedError",
        "fold_pipeline",
        "has_injectables",
        "SYNTHESIZED_CTX_PARAM_NAME",
        "TimeoutStage",
        "EnricherStage",
        "RouterLazyEnterStage",
        "DispatchHookStage",
        "LddStateStage",
        "ErrorCaptureStage",
    ):
        assert hasattr(dispatch, name), f"missing export: {name}"


def test_dispatch_package_imports_no_fastmcp() -> None:
    """The load-bearing constraint — the CLI consumer folds this pipeline."""
    code = "import sys\nimport a2kit.packages.dispatch\nprint('fastmcp' in sys.modules)"
    out = subprocess.run(  # noqa: S603
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True,
    )
    assert out.stdout.strip() == "False", "fastmcp leaked into a2kit.packages.dispatch"
