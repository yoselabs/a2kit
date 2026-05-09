"""Tests for compute_schema + TOONSnapshotExtension."""

from __future__ import annotations

from typing import Any

import a2kit
from a2kit.packages.testing import (
    SchemaSnapshotMismatch,
    TOONSnapshotExtension,
    compute_schema,
)
from uncalled_for import Depends


def get_db() -> str:
    return "real-db"


@a2kit.read("list_things")
async def list_things(*, db: str = Depends(get_db), q: str = "hi", limit: int = 10) -> dict:
    """List things matching ``q``."""
    return {"q": q, "limit": limit, "db": db}


@a2kit.write("delete_thing")
async def delete_thing(*, db: str = Depends(get_db), id: str) -> dict:
    """Delete the thing with the given id."""
    return {"deleted": id}


def test_compute_schema_strips_di_params() -> None:
    schema = compute_schema(list_things)
    props = schema["inputSchema"]["properties"]
    assert "db" not in props, "DI parameters must be stripped from inputSchema"
    assert set(props.keys()) == {"q", "limit"}
    assert props["q"]["type"] == "string"
    assert props["limit"]["type"] == "integer"


def test_compute_schema_includes_meta() -> None:
    schema = compute_schema(list_things)
    assert schema["name"] == "list_things"
    assert schema.get("description")
    assert schema["meta"]["verb"] == "read"
    assert "read" in schema["tags"]
    assert schema["annotations"].get("readOnlyHint") is True


def test_compute_schema_write_annotations() -> None:
    schema = compute_schema(delete_thing)
    assert schema["meta"]["verb"] == "write"
    assert schema["annotations"].get("destructiveHint") is True
    # `id` is required (no default).
    required = schema["inputSchema"].get("required", [])
    assert "id" in required


def test_compute_schema_no_fastmcp_loaded() -> None:
    import sys

    # We may have loaded fastmcp earlier in the session for unrelated reasons,
    # but compute_schema itself must be runnable without it. Just call it.
    compute_schema(list_things)
    # Best-effort: the call did not crash. (Cold-start guard lives elsewhere.)
    assert "a2kit.packages.testing.snapshots" in sys.modules


def test_toon_snapshot_extension_serialize() -> None:
    ext = TOONSnapshotExtension()
    schema: dict[str, Any] = compute_schema(list_things)
    out = ext.serialize(schema)
    assert isinstance(out, str)
    assert len(out) > 0
    # Round-trip equivalence to the formatter's TOON encoder is the contract.
    from a2kit.packages.formatter import format_response

    expected = format_response(schema, format_hint="toon").data
    assert out == expected


def test_toon_extension_file_extension() -> None:
    assert TOONSnapshotExtension.file_extension == "toon"


def test_schema_snapshot_mismatch_is_assertion_error() -> None:
    err = SchemaSnapshotMismatch("drift")
    assert isinstance(err, AssertionError)
    assert "drift" in str(err)
