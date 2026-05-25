"""BDD tests for A2kitConfig.ldd sub-model (ldd-log-level change).

Locks the runtime-config delta scenarios:
- Default level is "info"
- Env A2KIT_LDD__LEVEL=debug wins
- Env beats kwarg per ADR 0022
- Invalid level raises ValidationError at construction
- Kwarg wins when env is unset
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from a2kit.config import A2kitConfig, LddConfig


@pytest.fixture(autouse=True)
def _clear_a2kit_env(monkeypatch: pytest.MonkeyPatch) -> None:
    import os

    for k in list(os.environ):
        if k.startswith("A2KIT_"):
            monkeypatch.delenv(k, raising=False)


@pytest.fixture
def no_dotenv(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_default_level_is_info(no_dotenv: Path) -> None:
    cfg = A2kitConfig()
    assert cfg.ldd.level == "info"


def test_env_sets_level(monkeypatch: pytest.MonkeyPatch, no_dotenv: Path) -> None:
    monkeypatch.setenv("A2KIT_LDD__LEVEL", "debug")
    cfg = A2kitConfig()
    assert cfg.ldd.level == "debug"


def test_env_beats_kwarg(monkeypatch: pytest.MonkeyPatch, no_dotenv: Path) -> None:
    monkeypatch.setenv("A2KIT_LDD__LEVEL", "warning")
    cfg = A2kitConfig(ldd=LddConfig(level="trace"))
    assert cfg.ldd.level == "warning"


def test_kwarg_wins_when_env_unset(no_dotenv: Path) -> None:
    cfg = A2kitConfig(ldd=LddConfig(level="trace"))
    assert cfg.ldd.level == "trace"


def test_invalid_level_raises_at_construction(monkeypatch: pytest.MonkeyPatch, no_dotenv: Path) -> None:
    monkeypatch.setenv("A2KIT_LDD__LEVEL", "verbose")
    with pytest.raises(ValidationError):
        A2kitConfig()


def test_invalid_kwarg_raises(no_dotenv: Path) -> None:
    with pytest.raises(ValidationError):
        LddConfig(level="loud")  # ty: ignore[invalid-argument-type]


def test_all_documented_levels_accepted(no_dotenv: Path) -> None:
    for lvl in ("trace", "debug", "info", "warning", "error"):
        cfg = A2kitConfig(ldd=LddConfig(level=lvl))
        assert cfg.ldd.level == lvl


def test_uppercase_env_value_rejected(monkeypatch: pytest.MonkeyPatch, no_dotenv: Path) -> None:
    """Level values are case-sensitive (Literal). Env key is case-insensitive,
    but `A2KIT_LDD__LEVEL=DEBUG` raises — values must be lowercase."""
    monkeypatch.setenv("A2KIT_LDD__LEVEL", "DEBUG")
    with pytest.raises(ValidationError):
        A2kitConfig()
