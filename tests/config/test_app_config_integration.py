"""App(config=..., user_config=...) integration with A2kitConfig."""

from __future__ import annotations

from pathlib import Path

import pytest

import a2kit
from a2kit.config import A2kitConfig, McpConfig


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


def test_app_without_config_gets_fresh_a2kitconfig(no_dotenv: Path) -> None:
    app = a2kit.App("t")
    assert isinstance(app.config, A2kitConfig)
    assert app.config.mcp.structured_output is False


def test_app_with_explicit_config(no_dotenv: Path) -> None:
    cfg = A2kitConfig(mcp=McpConfig(structured_output=True))
    app = a2kit.App("t", config=cfg)
    assert app.config is cfg
    assert app.config.mcp.structured_output is True


def test_app_config_picks_up_env_at_construction(monkeypatch: pytest.MonkeyPatch, no_dotenv: Path) -> None:
    monkeypatch.setenv("A2KIT_MCP__STRUCTURED_OUTPUT", "true")
    app = a2kit.App("t")
    assert app.config.mcp.structured_output is True


def test_env_overrides_explicit_config_kwarg_via_config_construction(monkeypatch: pytest.MonkeyPatch, no_dotenv: Path) -> None:
    """ADR 0022: env beats code. Code-author's config kwarg is a suggestion."""
    monkeypatch.setenv("A2KIT_MCP__STRUCTURED_OUTPUT", "true")
    # Developer passes a "default suggestion" — env still wins.
    cfg = A2kitConfig(mcp=McpConfig(structured_output=False))
    app = a2kit.App("t", config=cfg)
    assert app.config.mcp.structured_output is True


def test_user_config_passes_through_unchanged(no_dotenv: Path) -> None:
    class MyOpaqueConfig:
        api_key = "secret"

    my = MyOpaqueConfig()
    app = a2kit.App("t", user_config=my)
    assert app.user_config is my


def test_user_config_defaults_to_none(no_dotenv: Path) -> None:
    app = a2kit.App("t")
    assert app.user_config is None


def test_user_config_not_merged_into_a2kitconfig(no_dotenv: Path) -> None:
    class MyOpaqueConfig:
        api_key = "secret"

    app = a2kit.App("t", user_config=MyOpaqueConfig())
    # The user-config fields are NOT visible on a2kit.config
    assert not hasattr(app.config, "api_key")
