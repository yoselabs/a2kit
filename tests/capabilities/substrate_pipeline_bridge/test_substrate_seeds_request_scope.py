"""Capability: every substrate seeds `request_scope` before folding the dispatch pipeline.

Encodes the inbound side of the substrate<->pipeline contract. Today this
test FAILS on HTTP (`packages/http/build.py` does not fold the pipeline at
all). Once `dispatch-pipeline-parity-on-http` lands, HTTP gains a
`_principal_middleware.py` that calls `request_scope.publish(principal)`
and `build.py` calls `fold_pipeline(...)` per projection tool.
"""

from __future__ import annotations

from pathlib import Path

_PKG_DIR = Path(__file__).resolve().parents[3] / "src" / "a2kit" / "packages"


def _file_or_dir_text(path: Path) -> str:
    """Concatenate every .py under `path` (or just read the file)."""
    if path.is_file():
        return path.read_text()
    return "\n".join(p.read_text() for p in sorted(path.rglob("*.py")))


def test_mcp_substrate_folds_the_pipeline() -> None:
    """MCP: `packages/mcp/server.py` calls `fold_pipeline` per tool."""
    text = (_PKG_DIR / "mcp" / "server.py").read_text()
    assert "fold_pipeline(" in text, "mcp/server.py MUST fold the dispatch pipeline"


def test_mcp_substrate_publishes_principal_via_request_scope() -> None:
    """MCP: somewhere under `packages/mcp/`, a middleware calls `request_scope.publish`."""
    text = _file_or_dir_text(_PKG_DIR / "mcp")
    assert "request_scope.publish(" in text, "mcp/ MUST publish Principal via request_scope.publish"


def test_http_substrate_folds_the_pipeline() -> None:
    """HTTP: `packages/http/build.py` calls `fold_pipeline` per projection tool.

    FAILS until `dispatch-pipeline-parity-on-http` task 5.1 lands.
    """
    text = (_PKG_DIR / "http" / "build.py").read_text()
    assert "fold_pipeline(" in text, (
        "http/build.py MUST fold the dispatch pipeline per projection tool. "
        "Today it bypasses the pipeline — see S13 in STRUCTURE_ISSUES.md."
    )


def test_http_substrate_publishes_principal_via_request_scope() -> None:
    """HTTP: somewhere under `packages/http/`, a middleware calls `request_scope.publish`.

    The seam moves out of the per-route `_apply_authorize_gate` (which scrapes
    kwargs and publishes) into a dedicated `_principal_middleware.py` that
    runs after auth middlewares for EVERY request, not just authorize-gated
    tools. FAILS until task 3.1 lands.
    """
    text = _file_or_dir_text(_PKG_DIR / "http")
    assert "request_scope.publish(" in text, (
        "http/ MUST publish Principal via request_scope.publish from a dedicated middleware (not per-route inside _apply_authorize_gate)."
    )
    # The seam must NOT live in _apply_authorize_gate anymore — that helper
    # deletes per task 5.3 of the change. Check for the DEFINITION
    # specifically; the symbol name may still appear in historical
    # docstrings noting the pre-refactor state.
    build_text = (_PKG_DIR / "http" / "build.py").read_text()
    assert "def _apply_authorize_gate" not in build_text, (
        "_apply_authorize_gate must be removed; the pipeline's AuthorizeGateStage "
        "covers the gate and the substrate-signature wrapper publishes the "
        "Principal once per request."
    )
