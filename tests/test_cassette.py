"""Tests for a2kit.testing.cassette — vcrpy thin passthrough."""

from __future__ import annotations

import builtins
from pathlib import Path
from typing import Any

import pytest

import a2kit
from a2kit import _cassette
from a2kit._cassette import cassette


class _FakeCassetteCtx:
    def __init__(self) -> None:
        self.entered = False

    def __enter__(self) -> _FakeCassetteCtx:
        self.entered = True
        return self

    def __exit__(self, *exc: object) -> None:
        return None


class _FakeVcr:
    def __init__(self) -> None:
        self.last_path: str | None = None
        self.last_mode: str | None = None

    def use_cassette(self, path: str, record_mode: str | None = None) -> _FakeCassetteCtx:
        self.last_path = path
        self.last_mode = record_mode
        return _FakeCassetteCtx()


@pytest.fixture
def fake_vcr(monkeypatch: pytest.MonkeyPatch) -> _FakeVcr:
    fake = _FakeVcr()
    monkeypatch.setattr(_cassette, "_import_vcr", lambda: fake)
    return fake


def test_cassette_context_manager_sync(tmp_path: Path, fake_vcr: _FakeVcr) -> None:
    p = tmp_path / "c.yaml"
    with cassette(p):
        pass
    assert fake_vcr.last_path == str(p)
    assert fake_vcr.last_mode == "once"  # missing file → record


def test_cassette_replay_when_file_exists(tmp_path: Path, fake_vcr: _FakeVcr) -> None:
    p = tmp_path / "c.yaml"
    p.write_text("ok")
    with cassette(p):
        pass
    assert fake_vcr.last_mode == "none"


def test_cassette_explicit_record_mode(tmp_path: Path, fake_vcr: _FakeVcr) -> None:
    with cassette(tmp_path / "c.yaml", record_mode="all"):
        pass
    assert fake_vcr.last_mode == "all"


def test_cassette_creates_parent_dir(tmp_path: Path, fake_vcr: _FakeVcr) -> None:
    nested = tmp_path / "deep" / "nested" / "c.yaml"
    with cassette(nested):
        pass
    assert nested.parent.exists()


def test_cassette_re_export_from_testing(tmp_path: Path, fake_vcr: _FakeVcr) -> None:
    obj = a2kit.testing.cassette(tmp_path / "c.yaml")
    assert isinstance(obj, _FakeCassetteCtx)


def test_cassette_missing_vcr_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    real_import = builtins.__import__

    def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "vcr":
            raise ImportError("no vcr")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(ImportError, match="vcrpy"):
        cassette(tmp_path / "c.yaml")
