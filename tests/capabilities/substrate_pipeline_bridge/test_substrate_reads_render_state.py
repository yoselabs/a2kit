"""Capability: every substrate reads `_render_state` after the pipeline raises.

Encodes the outbound side of the substrate<->pipeline contract. Today this
test FAILS on HTTP — `packages/http/build.py` re-derives the
`AppError → status` mapping inline in `_http_status_for` instead of reading
the rendered envelope from `_render_state` via `get_rendered_error(exc)`.

Once `dispatch-pipeline-parity-on-http` lands, HTTP gains an
`HttpErrorRenderStage` that calls `get_rendered_error(exc)` and renders a
`JSONResponse` from the `RenderedError`.
"""

from __future__ import annotations

from pathlib import Path

_PKG_DIR = Path(__file__).resolve().parents[3] / "src" / "a2kit" / "packages"


def _files_text(*paths: Path) -> str:
    out: list[str] = []
    for p in paths:
        if p.is_file():
            out.append(p.read_text())
        elif p.is_dir():
            out.extend(sub.read_text() for sub in sorted(p.rglob("*.py")))
    return "\n".join(out)


def test_mcp_render_stage_uses_typed_accessor() -> None:
    """MCP: `_wrappers.py` (which hosts `McpErrorRenderStage`) calls `get_rendered_error`."""
    text = (_PKG_DIR / "mcp" / "_wrappers.py").read_text()
    assert "get_rendered_error(" in text, "MCP render stage MUST read via get_rendered_error"


def test_cli_render_stage_uses_typed_accessor() -> None:
    """CLI: the cli runtime / error-render stage calls `get_rendered_error`."""
    text = _files_text(_PKG_DIR / "cli")
    assert "get_rendered_error(" in text, "CLI render stage MUST read via get_rendered_error"


def test_http_render_path_uses_typed_accessor() -> None:
    """HTTP: somewhere under `packages/http/`, the error-render path calls `get_rendered_error`.

    FAILS until task 4.1 (`HttpErrorRenderStage`) lands.
    """
    text = _files_text(_PKG_DIR / "http")
    assert "get_rendered_error(" in text, (
        "http/ MUST read the rendered error envelope via get_rendered_error. "
        "Today it re-derives the kind->status mapping in _http_status_for — "
        "see S11 in STRUCTURE_ISSUES.md."
    )


def test_http_no_inline_kind_to_status_map() -> None:
    """HTTP: the `_KIND_HTTP_STATUS` table is removed once the render stage owns the mapping.

    The canonical kind->status map lives in `RenderedError.http_status`,
    populated by `ErrorEnvelopeStage` during pipeline fold. The substrate's
    render stage SHALL just read that field, not re-derive it.

    FAILS until task 6.1 lands.
    """
    text = (_PKG_DIR / "http" / "build.py").read_text()
    assert "_KIND_HTTP_STATUS" not in text, (
        "build.py MUST NOT carry its own kind->status map. The render stage reads RenderedError.http_status from `_render_state`."
    )
