"""Atomic-save behaviour: tempfile + rename + chmod, no partial writes visible."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from a2kit import ConnectionStore

from .conftest import DbInfo


async def test_save_uses_tempfile_then_rename(db_store: ConnectionStore[DbInfo], monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify a tempfile is created and replaced, not direct-written."""
    seen_tmp_writes: list[str] = []
    original_replace = Path.replace

    def tracking_replace(self: Path, target: str | Path) -> Path:
        seen_tmp_writes.append(self.name)
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", tracking_replace)
    await db_store.save(DbInfo(key=("a", "b", "c"), dsn="sqlite://"))
    assert len(seen_tmp_writes) == 1
    assert seen_tmp_writes[0].endswith(".tmp")
    assert seen_tmp_writes[0].startswith(".a-b-c.")


async def test_save_replaces_existing_atomically(db_store: ConnectionStore[DbInfo]) -> None:
    """Two saves to the same key produce one final file with the latest content."""
    await db_store.save(DbInfo(key=("a", "b", "c"), dsn="sqlite:///v1.db"))
    await db_store.save(DbInfo(key=("a", "b", "c"), dsn="sqlite:///v2.db"))
    files = list(db_store.config_dir.glob("*"))
    # Exactly one final file, no leftover tmp.
    assert len(files) == 1
    assert files[0].name == "a-b-c.toml"
    loaded = await db_store.load(("a", "b", "c"))
    assert loaded.dsn == "sqlite:///v2.db"


async def test_chmod_sets_owner_only(db_store: ConnectionStore[DbInfo]) -> None:
    path = await db_store.save(DbInfo(key=("a", "b", "c"), dsn="sqlite://"))
    mode = os.stat(path).st_mode & 0o777
    assert mode == 0o600
