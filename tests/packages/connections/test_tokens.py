"""tokens module: env / op:// resolvers + failure modes."""

from __future__ import annotations

import shutil
import subprocess

import pytest

from a2kit.packages.connections.exceptions import EnvVarNotFound, OpResolutionError
from a2kit.packages.connections.tokens import (
    has_env_ref,
    is_op_ref,
    resolve_env,
    resolve_op,
    resolve_value,
)


def test_resolve_env_substitutes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MY_TOKEN", "abc")
    assert resolve_env("Bearer ${MY_TOKEN}") == "Bearer abc"


def test_resolve_env_missing_var() -> None:
    with pytest.raises(EnvVarNotFound):
        resolve_env("${MISSING_VAR}")


def test_resolve_env_no_ref_passthrough() -> None:
    assert resolve_env("plain") == "plain"


def test_op_ref_detection() -> None:
    assert is_op_ref("op://vault/item/field")
    assert not is_op_ref("not-op")


def test_env_ref_detection() -> None:
    assert has_env_ref("${X}")
    assert not has_env_ref("nope")


def test_resolve_op_no_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    with pytest.raises(OpResolutionError):
        resolve_op("op://vault/item/field")


def test_resolve_op_called_process_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/local/bin/op")

    def _raise(*_a, **_kw):  # type: ignore[no-untyped-def]
        raise subprocess.CalledProcessError(1, ["op"], output="", stderr="auth required")

    monkeypatch.setattr(subprocess, "run", _raise)
    with pytest.raises(OpResolutionError) as ei:
        resolve_op("op://vault/item/field")
    assert "auth required" in str(ei.value)


def test_resolve_op_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/local/bin/op")

    def _raise(*_a, **_kw):  # type: ignore[no-untyped-def]
        raise subprocess.TimeoutExpired(cmd=["op"], timeout=10)

    monkeypatch.setattr(subprocess, "run", _raise)
    with pytest.raises(OpResolutionError):
        resolve_op("op://vault/item/field")


def test_resolve_value_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MY_TOKEN", "abc")
    assert resolve_value("plain") == "plain"
    assert resolve_value("${MY_TOKEN}") == "abc"

    class _R:
        stdout = "secret\n"
        stderr = ""
        returncode = 0

    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/local/bin/op")
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: _R())
    assert resolve_value("op://v/i/f") == "secret"
