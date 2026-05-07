"""Schema snapshot harness — the keystone primitive.

The shared gap surfaced by both reference MCPs (`learnings/a2db.md`,
`learnings/a2atlassian.md`, `modules/dev-quality.md`): there's no first-class
artefact that ties tool-schema drift detection to the token-budget contract. This
module ships it.

Two operations:

- `snapshot_schemas(server, snapshot_dir)` — writes one `<tool>.json` per tool
  registered on the FastMCP server. Compact JSON (no indent), so
  `os.path.getsize()` is the actual token-budget proxy.
- `assert_schemas_match(server, snapshot_dir)` — loads existing snapshots,
  compares against current. Raises `SchemaSnapshotMismatch` with a unified diff.

A `pytest` fixture (`schema_snapshot`) and a CLI flag
(`--update-schema-snapshots`) are wired via the `pytest_a2kit` plugin (see
`pytest_plugin.py`). On first run the fixture writes; on subsequent runs it
asserts.

## FastMCP integration note

FastMCP exposes registered tools via `server._tool_manager.list_tools()` — each
`Tool` object has `.name`, `.description`, `.parameters` (JSON schema for inputs)
and `.output_schema` (JSON schema for outputs, or `None`). Pinned to
`mcp >= 1.0`. If the underscore-prefixed attribute path moves in a future FastMCP
release, `_extract_tool_schema` is the single seam to update — every other
function in this module routes through it.
"""

from __future__ import annotations

import difflib
import json
from typing import TYPE_CHECKING, Any

from a2kit.exceptions import SchemaSnapshotMismatch

if TYPE_CHECKING:
    from pathlib import Path

    from mcp.server.fastmcp import FastMCP


def _list_tools(server: FastMCP) -> list[Any]:
    """Return registered Tool objects from a FastMCP server.

    Workaround: FastMCP's public surface for listing tools is async
    (`server.list_tools()`), but the internal `_tool_manager.list_tools()` is
    synchronous and returns the same `Tool` objects with `.parameters` /
    `.output_schema` accessible. We use the sync path so this harness can be
    called from non-async test code. Pinned at `mcp >= 1.0`. If the path
    changes, this is the only seam to update.
    """
    return list(server._tool_manager.list_tools())  # noqa: SLF001


def _extract_tool_schema(tool: Any) -> dict[str, Any]:
    """Extract the schema dict for a single FastMCP `Tool`."""
    out: dict[str, Any] = {
        "name": tool.name,
        "description": tool.description or "",
        "input_schema": tool.parameters,
    }
    if getattr(tool, "output_schema", None) is not None:
        out["output_schema"] = tool.output_schema
    return out


def _serialise(schema: dict[str, Any]) -> str:
    """Compact JSON for byte-accurate token-budget comparison."""
    return json.dumps(schema, sort_keys=True, separators=(",", ":"))


def snapshot_schemas(server: FastMCP, snapshot_dir: Path) -> dict[str, Path]:
    """Write one snapshot file per tool. Returns `{tool_name: file_path}`.

    Files are compact JSON (no indent) because the file size is the contract:
    `os.path.getsize(snapshot_dir / 'my_tool.json')` is the byte-accurate
    proxy for the per-tool token budget.
    """
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    out: dict[str, Path] = {}
    for tool in _list_tools(server):
        schema = _extract_tool_schema(tool)
        path = snapshot_dir / f"{tool.name}.json"
        path.write_text(_serialise(schema), encoding="utf-8")
        out[tool.name] = path
    return out


def _diff(name: str, expected: str, actual: str) -> str:
    return "\n".join(
        difflib.unified_diff(
            expected.splitlines(),
            actual.splitlines(),
            fromfile=f"{name} (snapshot)",
            tofile=f"{name} (current)",
            lineterm="",
        )
    )


def assert_schemas_match(server: FastMCP, snapshot_dir: Path) -> None:
    """Compare current schemas against on-disk snapshots.

    Raises `SchemaSnapshotMismatch` on any difference (added tool, removed tool,
    or changed schema). The message contains a unified diff per affected tool.
    """
    if not snapshot_dir.exists():
        msg = f"Snapshot directory does not exist: {snapshot_dir}. Run with --update-schema-snapshots."
        raise SchemaSnapshotMismatch(msg)

    current: dict[str, str] = {}
    for tool in _list_tools(server):
        current[tool.name] = _serialise(_extract_tool_schema(tool))

    saved: dict[str, str] = {}
    for path in snapshot_dir.glob("*.json"):
        saved[path.stem] = path.read_text(encoding="utf-8")

    problems: list[str] = []
    for name in sorted(set(current) | set(saved)):
        if name not in saved:
            problems.append(f"New tool not in snapshots: {name}")
            continue
        if name not in current:
            problems.append(f"Tool removed from server but snapshot remains: {name}")
            continue
        if current[name] != saved[name]:
            problems.append(_diff(name, saved[name], current[name]))

    if problems:
        joined = "\n\n".join(problems)
        msg = f"Schema snapshot mismatch:\n{joined}\n\nRe-run with --update-schema-snapshots to accept."
        raise SchemaSnapshotMismatch(msg)


def cassette(path: Any, *, record_mode: str | None = None) -> Any:
    """Re-export of `a2kit._cassette.cassette` — only imported when called.

    The `vcrpy` dep is in the optional `[testing]` extra; lazy import keeps the
    minimal install free of it.
    """
    from a2kit._cassette import cassette as _impl  # noqa: PLC0415

    return _impl(path, record_mode=record_mode)


__all__ = ["assert_schemas_match", "cassette", "snapshot_schemas"]
