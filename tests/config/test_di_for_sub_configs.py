"""BDD tests for config-DI provider registration (di-for-sub-configs change).

Locks the config-di-providers + runtime-config + di-container-package +
ldd-level-threshold delta scenarios. The contract: A2kitConfig and each
sub-config are DI-resolvable; resolution identity-matches `app.config.<sub>`;
user `app.provide(LddConfig, fake)` wins last-write-wins per ADR 0006.
"""

from __future__ import annotations

import pytest

import a2kit
from a2kit.config import A2kitConfig, CliConfig, HttpConfig, LddConfig, McpConfig


@pytest.mark.asyncio
async def test_a2kitconfig_resolves_via_di_to_appconfig_instance() -> None:
    app = a2kit.App("svc", config=A2kitConfig(debug=True))
    async with app._container:
        cfg = await app._container.get(A2kitConfig)
    assert cfg is app.config
    assert cfg.debug is True


@pytest.mark.asyncio
async def test_lddconfig_resolves_via_di_to_appconfig_ldd() -> None:
    app = a2kit.App("svc", config=A2kitConfig(ldd=LddConfig(level="debug")))
    async with app._container:
        ldd = await app._container.get(LddConfig)
    assert ldd is app.config.ldd
    assert ldd.level == "debug"


@pytest.mark.asyncio
async def test_mcpconfig_resolves_to_same_instance_as_appconfig_mcp() -> None:
    app = a2kit.App("svc")
    async with app._container:
        mcp = await app._container.get(McpConfig)
    assert mcp is app.config.mcp


@pytest.mark.asyncio
async def test_all_sub_configs_registered() -> None:
    """Smoke: HttpConfig and CliConfig also resolve via DI even though
    they are currently empty stubs (di-container-package contract:
    framework-owned providers seeded at App construction)."""
    app = a2kit.App("svc")
    async with app._container:
        http = await app._container.get(HttpConfig)
        cli = await app._container.get(CliConfig)
    assert http is app.config.http
    assert cli is app.config.cli


@pytest.mark.asyncio
async def test_user_provide_overrides_lddconfig_default() -> None:
    """ADR 0006 last-write-wins: a user `provide(LddConfig, ...)` after
    `App.__init__` MUST replace the framework-seeded provider."""
    fake = LddConfig(level="trace")
    app = a2kit.App("svc")
    app.provide(LddConfig, lambda: fake)
    async with app._container:
        resolved = await app._container.get(LddConfig)
    assert resolved is fake
    assert resolved is not app.config.ldd


def test_app_debug_attribute_raises_with_migration_hint() -> None:
    """`App.debug` is removed; access raises with hint pointing at both
    the consumer (`app.config.debug`) and subsystem (DI) replacements."""
    app = a2kit.App("svc")
    with pytest.raises(AttributeError) as ei:
        _ = app.debug  # type: ignore[attr-defined]
    msg = str(ei.value)
    assert "App.debug was removed" in msg
    assert "app.config.debug" in msg
    assert "A2kitConfig" in msg


def test_app_config_remains_public_attribute() -> None:
    """`app.config` is the consumer-facing introspection surface and
    MUST remain a readable attribute (only the `debug` shortcut goes
    away)."""
    app = a2kit.App("svc", config=A2kitConfig(debug=True))
    assert isinstance(app.config, A2kitConfig)
    assert app.config.debug is True
