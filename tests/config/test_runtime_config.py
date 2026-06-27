"""BDD tests for the runtime-config capability (ADR 0022).

Covers the invariants from openspec/specs/runtime-config/spec.md:
- A2kitConfig instantiates with documented defaults
- Env vars override init kwargs (inverted source order — consumer beats code)
- Double-underscore nesting works; single underscore is part of field name
- .env file ranks above init kwargs
- No public freeze / lock / bypass surface exists
"""

from __future__ import annotations

from pathlib import Path

import pytest

from a2kit.config import A2kitConfig, McpConfig


@pytest.fixture(autouse=True)
def _clear_a2kit_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip ambient A2KIT_* env so tests are deterministic."""
    import os

    for k in list(os.environ):
        if k.startswith("A2KIT_"):
            monkeypatch.delenv(k, raising=False)


@pytest.fixture
def no_dotenv(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Chdir into a tmp dir so no ambient .env interferes."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


# ----- Defaults ---------------------------------------------------------- #


def test_defaults(no_dotenv: Path) -> None:
    cfg = A2kitConfig()
    assert cfg.mcp.structured_output is False


def test_code_mode_default_true(no_dotenv: Path) -> None:
    cfg = A2kitConfig()
    assert cfg.mcp.code_mode is True


def test_code_mode_env_sets_false(monkeypatch: pytest.MonkeyPatch, no_dotenv: Path) -> None:
    monkeypatch.setenv("A2KIT_MCP__CODE_MODE", "false")
    cfg = A2kitConfig()
    assert cfg.mcp.code_mode is False


def test_code_mode_env_beats_kwarg(monkeypatch: pytest.MonkeyPatch, no_dotenv: Path) -> None:
    monkeypatch.setenv("A2KIT_MCP__CODE_MODE", "false")
    cfg = A2kitConfig(mcp=McpConfig(code_mode=True))
    assert cfg.mcp.code_mode is False


# ----- Env beats kwargs (the load-bearing inversion) --------------------- #


def test_env_overrides_kwarg(monkeypatch: pytest.MonkeyPatch, no_dotenv: Path) -> None:
    monkeypatch.setenv("A2KIT_MCP__STRUCTURED_OUTPUT", "true")
    cfg = A2kitConfig(mcp=McpConfig(structured_output=False))
    assert cfg.mcp.structured_output is True


def test_env_overrides_default(monkeypatch: pytest.MonkeyPatch, no_dotenv: Path) -> None:
    monkeypatch.setenv("A2KIT_MCP__STRUCTURED_OUTPUT", "true")
    cfg = A2kitConfig()
    assert cfg.mcp.structured_output is True


def test_kwarg_wins_when_env_unset(no_dotenv: Path) -> None:
    cfg = A2kitConfig(mcp=McpConfig(structured_output=True))
    assert cfg.mcp.structured_output is True


# ----- Env convention ---------------------------------------------------- #


def test_case_insensitive_bool(monkeypatch: pytest.MonkeyPatch, no_dotenv: Path) -> None:
    monkeypatch.setenv("A2KIT_MCP__STRUCTURED_OUTPUT", "TRUE")
    cfg = A2kitConfig()
    assert cfg.mcp.structured_output is True


def test_single_underscore_is_part_of_field_name(monkeypatch: pytest.MonkeyPatch, no_dotenv: Path) -> None:
    """Single _ in STRUCTURED_OUTPUT is not nesting; it is the field name."""
    monkeypatch.setenv("A2KIT_MCP__STRUCTURED_OUTPUT", "true")
    cfg = A2kitConfig()
    assert cfg.mcp.structured_output is True


def test_unknown_env_ignored(monkeypatch: pytest.MonkeyPatch, no_dotenv: Path) -> None:
    monkeypatch.setenv("A2KIT_UNKNOWN__FIELD", "value")
    # Should not raise — extra="ignore" on the config.
    A2kitConfig()


# ----- .env file ranks above kwargs -------------------------------------- #


def test_dotenv_overrides_kwarg(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("A2KIT_MCP__STRUCTURED_OUTPUT=true\n")
    monkeypatch.chdir(tmp_path)
    cfg = A2kitConfig(mcp=McpConfig(structured_output=False))
    assert cfg.mcp.structured_output is True


def test_process_env_overrides_dotenv(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("A2KIT_MCP__STRUCTURED_OUTPUT=false\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("A2KIT_MCP__STRUCTURED_OUTPUT", "true")
    cfg = A2kitConfig()
    assert cfg.mcp.structured_output is True


# ----- No freeze / lock / bypass surface --------------------------------- #


def test_no_freeze_kwarg_takes_effect(monkeypatch: pytest.MonkeyPatch, no_dotenv: Path) -> None:
    """ADR 0022: no `frozen` field exists on A2kitConfig — extra kwargs are ignored.

    The guarantee is that no code path can prevent env from winning.
    Passing `frozen=True` must NOT lock structured_output against env override.
    """
    monkeypatch.setenv("A2KIT_MCP__STRUCTURED_OUTPUT", "true")
    cfg = A2kitConfig(frozen=True, mcp=McpConfig(structured_output=False))  # ty: ignore[unknown-argument]
    # Env still wins. The `frozen=True` is silently ignored — it has no effect.
    assert cfg.mcp.structured_output is True
    assert "frozen" not in A2kitConfig.model_fields


def test_no_bypass_env_symbols() -> None:
    """No symbol in a2kit.config has a name containing freeze/lock/bypass/pinned."""
    import a2kit.config as mod

    bad = {"freeze", "lock", "bypass", "pinned"}
    for name in dir(mod):
        lower = name.lower()
        for token in bad:
            assert token not in lower, f"a2kit.config exposes a {token!r}-shaped symbol: {name}"
