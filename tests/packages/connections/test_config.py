"""ConnectionConfig: BaseSettings, Key arity, eager substitution, raw round-trip."""

from __future__ import annotations


import pytest

from a2kit.packages.connections import (
    ConnectionConfig,
    EnvVarNotFound,
    KeyArityMismatch,
    OpResolutionError,
)
from .conftest import TripleConfig, TripleKey, WidgetConfig


def test_eager_env_substitution(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MY_TOKEN", "real-secret-123")
    cfg = WidgetConfig(key=("prod",), token="${MY_TOKEN}")
    assert cfg.token == "real-secret-123"


def test_missing_env_var_fails_fast() -> None:
    with pytest.raises(EnvVarNotFound):
        WidgetConfig(key=("prod",), token="${MISSING_VAR}")


def test_raw_preserves_placeholder_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MY_TOKEN", "real-secret-123")
    cfg = WidgetConfig(key=("prod",), token="${MY_TOKEN}")
    assert cfg.token == "real-secret-123"
    raw = cfg.serialize_to_disk()
    assert raw["token"] == "${MY_TOKEN}"
    assert "real-secret" not in str(raw)


def test_key_arity_namedtuple() -> None:
    cfg = TripleConfig(key=TripleKey("p", "dev", "db1"), token="t")
    assert cfg.key == ("p", "dev", "db1")


def test_key_arity_mismatch_raises() -> None:
    # pydantic wraps custom validator errors in ValidationError; original
    # KeyArityMismatch is reachable via .errors()[0]['ctx']['error'].
    from pydantic import ValidationError

    with pytest.raises((KeyArityMismatch, ValidationError)) as ei:
        TripleConfig(key=("p", "dev"), token="t")
    if isinstance(ei.value, ValidationError):
        inner = ei.value.errors()[0].get("ctx", {}).get("error")
        assert isinstance(inner, KeyArityMismatch)


def test_default_key_single_field() -> None:
    cfg = WidgetConfig(key=("prod",), token="literal")
    assert cfg.token == "literal"
    assert cfg.filename == "prod.toml"


def test_subclass_key_must_be_namedtuple() -> None:
    with pytest.raises(TypeError):

        class _Bad(ConnectionConfig, key=tuple):  # type: ignore[misc]
            token: str


def test_op_resolution_failure_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    import shutil as _shutil

    monkeypatch.setattr(_shutil, "which", lambda _name: None)
    with pytest.raises(OpResolutionError):
        WidgetConfig(key=("prod",), token="op://vault/item/field")


def test_op_resolution_subprocess_success(monkeypatch: pytest.MonkeyPatch) -> None:
    import shutil as _shutil
    import subprocess as _sp

    class _R:
        stdout = "secret-from-op\n"
        stderr = ""
        returncode = 0

    monkeypatch.setattr(_shutil, "which", lambda _name: "/usr/local/bin/op")
    monkeypatch.setattr(_sp, "run", lambda *a, **kw: _R())
    cfg = WidgetConfig(key=("prod",), token="op://vault/item/field")
    assert cfg.token == "secret-from-op"
    assert cfg.serialize_to_disk()["token"] == "op://vault/item/field"
