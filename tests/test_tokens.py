"""Token resolver tests: env, op, literal, registry."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from a2kit import (
    EnvVarNotFound,
    OpResolutionError,
    ResolverRegistry,
    default_registry,
    resolve_env,
    resolve_literal,
    resolve_op,
    resolve_token,
)


# -- ${ENV_VAR} --------------------------------------------------------------


def test_resolve_env_expands(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FOO", "bar")
    assert resolve_env("${FOO}") == "bar"


def test_resolve_env_partial_string(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("X", "abc")
    assert resolve_env("prefix-${X}-suffix") == "prefix-abc-suffix"


def test_resolve_env_passthrough_when_no_ref() -> None:
    assert resolve_env("plain-string") == "plain-string"


def test_resolve_env_missing_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEFINITELY_NOT_SET_XYZ", raising=False)
    with pytest.raises(EnvVarNotFound) as excinfo:
        resolve_env("${DEFINITELY_NOT_SET_XYZ}")
    assert excinfo.value.var == "DEFINITELY_NOT_SET_XYZ"
    assert "DEFINITELY_NOT_SET_XYZ" in excinfo.value.ref


# -- op:// -------------------------------------------------------------------


def test_resolve_op_success(fake_op_bin: Path) -> None:
    assert resolve_op("op://vault/item/field") == "secret-from-op"


def test_resolve_op_missing_binary_raises(no_op_bin: None) -> None:
    with pytest.raises(OpResolutionError) as excinfo:
        resolve_op("op://vault/item/field")
    assert "op" in excinfo.value.hint
    assert excinfo.value.ref == "op://vault/item/field"


def test_resolve_op_failure_raises(fake_op_bin: Path) -> None:
    with pytest.raises(OpResolutionError) as excinfo:
        resolve_op("op://fail/item/field")
    assert "session expired" in excinfo.value.hint


def test_resolve_op_timeout_raises(fake_op_bin: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    real_run = subprocess.run

    def fast_timeout(*args, **kwargs):  # type: ignore[no-untyped-def]
        kwargs["timeout"] = 0.01
        return real_run(*args, **kwargs)

    monkeypatch.setattr("a2kit.tokens.subprocess.run", fast_timeout)
    with pytest.raises(OpResolutionError) as excinfo:
        resolve_op("op://timeout/item/field")
    assert "timed out" in excinfo.value.hint


# -- literal -----------------------------------------------------------------


def test_resolve_literal_passthrough() -> None:
    assert resolve_literal("anything-at-all") == "anything-at-all"


# -- registry ----------------------------------------------------------------


def test_resolve_token_dispatches_to_op(fake_op_bin: Path) -> None:
    assert resolve_token("op://vault/item/field") == "secret-from-op"


def test_resolve_token_dispatches_to_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATOK", "value")
    assert resolve_token("${ATOK}") == "value"


def test_resolve_token_falls_back_to_literal() -> None:
    assert resolve_token("plain-secret-value") == "plain-secret-value"


def test_default_registry_is_module_global() -> None:
    assert default_registry() is default_registry()


def test_custom_registry_isolates_rules(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATOK", "from-env")
    custom = ResolverRegistry()
    custom.register(lambda v: v.startswith("rev:"), lambda v: v[4:][::-1])
    assert custom.resolve("rev:hello") == "olleh"
    # custom registry doesn't include env resolver
    assert custom.resolve("${ATOK}") == "${ATOK}"
    # but global still does
    assert resolve_token("${ATOK}") == "from-env"


def test_resolve_token_with_explicit_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XX", "yy")
    custom = ResolverRegistry()
    custom.register(lambda v: "${" in v, resolve_env)
    assert resolve_token("${XX}", registry=custom) == "yy"


def test_registry_first_match_wins() -> None:
    custom = ResolverRegistry()
    custom.register(lambda v: True, lambda v: "first")
    custom.register(lambda v: True, lambda v: "second")
    assert custom.resolve("anything") == "first"
