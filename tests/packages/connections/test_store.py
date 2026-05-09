"""ConnectionStore: save/load/delete, round-trip preserves placeholders, fail-fast at load."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from a2kit.packages.connections import ConnectionNotFound, ConnectionStore, EnvVarNotFound
from .conftest import WidgetConfig


def _run(coro):  # type: ignore[no-untyped-def]
    return asyncio.run(coro)


def test_save_then_load_preserves_placeholder(
    widget_store: ConnectionStore[WidgetConfig],
    cfg_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MY_TOKEN", "real-secret-123")
    cfg = WidgetConfig(key=("prod",), token="${MY_TOKEN}")
    path = _run(widget_store.save(cfg))
    assert path == cfg_dir / "prod.toml"
    on_disk = path.read_text()
    assert "${MY_TOKEN}" in on_disk
    assert "real-secret-123" not in on_disk
    loaded = _run(widget_store.load(("prod",)))
    assert loaded.token == "real-secret-123"


def test_load_missing_env_var_fails(widget_store: ConnectionStore[WidgetConfig]) -> None:
    cfg_path = widget_store.config_dir
    cfg_path.mkdir(parents=True, exist_ok=True)
    (cfg_path / "prod.toml").write_text('key = ["prod"]\ntoken = "${MISSING_VAR}"\nurl = ""\n')
    with pytest.raises(EnvVarNotFound):
        _run(widget_store.load(("prod",)))


def test_load_not_found(widget_store: ConnectionStore[WidgetConfig]) -> None:
    with pytest.raises(ConnectionNotFound):
        _run(widget_store.load(("ghost",)))


def test_delete(widget_store: ConnectionStore[WidgetConfig]) -> None:
    cfg = WidgetConfig(key=("prod",), token="literal")
    _run(widget_store.save(cfg))
    _run(widget_store.delete(("prod",)))
    with pytest.raises(ConnectionNotFound):
        _run(widget_store.delete(("prod",)))


def test_list_connections_sorted(widget_store: ConnectionStore[WidgetConfig]) -> None:
    for name in ("b", "a", "c"):
        _run(widget_store.save(WidgetConfig(key=(name,), token="literal")))
    listed = _run(widget_store.list_connections())
    assert [c.key for c in listed] == [("a",), ("b",), ("c",)]
