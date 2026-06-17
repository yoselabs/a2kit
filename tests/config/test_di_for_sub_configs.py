"""BDD tests for config-DI provider registration (di-for-sub-configs change).

Locks the config-di-providers + runtime-config + di-container-package +
log-level-threshold delta scenarios. The contract: A2kitConfig and each
sub-config are DI-resolvable; resolution identity-matches `app.config.<sub>`;
user `app.provide(LogConfig, fake)` wins last-write-wins per ADR 0006.
"""

from __future__ import annotations

import pytest

from a2kit.config import A2kitConfig, CliConfig, HttpConfig, LogConfig, McpConfig
from a2kit.testing import app_of


@pytest.mark.asyncio
async def test_a2kitconfig_resolves_via_di_to_appconfig_instance() -> None:
    app = app_of("svc", config=A2kitConfig(debug=True))
    async with app._container:
        cfg = await app._container.get(A2kitConfig)
    assert cfg is app.config
    assert cfg.debug is True


@pytest.mark.asyncio
async def test_logconfig_resolves_via_di_to_appconfig_log() -> None:
    app = app_of("svc", config=A2kitConfig(log=LogConfig(level="debug")))
    async with app._container:
        log = await app._container.get(LogConfig)
    assert log is app.config.log
    assert log.level == "debug"


@pytest.mark.asyncio
async def test_mcpconfig_resolves_to_same_instance_as_appconfig_mcp() -> None:
    app = app_of("svc")
    async with app._container:
        mcp = await app._container.get(McpConfig)
    assert mcp is app.config.mcp


@pytest.mark.asyncio
async def test_all_sub_configs_registered() -> None:
    """Smoke: HttpConfig and CliConfig also resolve via DI even though
    they are currently empty stubs (di-container-package contract:
    framework-owned providers seeded at App construction)."""
    app = app_of("svc")
    async with app._container:
        http = await app._container.get(HttpConfig)
        cli = await app._container.get(CliConfig)
    assert http is app.config.http
    assert cli is app.config.cli


@pytest.mark.asyncio
async def test_user_provide_overrides_logconfig_default() -> None:
    """ADR 0006 last-write-wins: a user `provide(LogConfig, ...)` after
    `App.__init__` MUST replace the framework-seeded provider."""
    fake = LogConfig(level="trace")
    app = app_of("svc")
    app.provide(LogConfig, lambda: fake)
    async with app._container:
        resolved = await app._container.get(LogConfig)
    assert resolved is fake
    assert resolved is not app.config.log


def test_app_debug_attribute_raises_plain_attributeerror() -> None:
    """`App.debug` is removed; access raises the language-default
    `AttributeError` (tombstone sunset — no bespoke hint). Consumers read
    `app.config.debug`; subsystems resolve `A2kitConfig` via DI."""
    app = app_of("svc")
    with pytest.raises(AttributeError) as ei:
        _ = app.debug  # type: ignore[attr-defined]
    msg = str(ei.value)
    assert "debug" in msg
    assert "App.debug was removed" not in msg


def test_app_config_remains_public_attribute() -> None:
    """`app.config` is the consumer-facing introspection surface and
    MUST remain a readable attribute (only the `debug` shortcut goes
    away)."""
    app = app_of("svc", config=A2kitConfig(debug=True))
    assert isinstance(app.config, A2kitConfig)
    assert app.config.debug is True
