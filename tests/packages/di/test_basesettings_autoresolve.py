"""BDD: pydantic-settings ``BaseSettings`` subclasses auto-resolve without registration.

Covers spec ``app-singletons`` (added requirement): when a tool param annotation
is a ``BaseSettings`` subclass and no explicit provider is registered, the
container constructs ``T()`` (zero-arg; pydantic reads env) and caches at
app-scope. Non-``BaseSettings`` types do NOT auto-resolve.
"""

from __future__ import annotations


import pytest
from pydantic_settings import BaseSettings, SettingsConfigDict

import a2kit


class _SmtpSettings(BaseSettings):
    host: str = "default-host"
    port: int = 587

    model_config = SettingsConfigDict(env_prefix="A2KIT_TEST_SMTP_")


class _NotSettings:
    """Plain class — must NOT be auto-resolved."""

    def __init__(self) -> None:
        self.flag = True


@pytest.mark.asyncio
async def test_basesettings_subclass_auto_resolved(monkeypatch: pytest.MonkeyPatch) -> None:
    """A ``BaseSettings`` subclass requested via the container is auto-constructed from env."""
    monkeypatch.setenv("A2KIT_TEST_SMTP_HOST", "envhost")
    monkeypatch.setenv("A2KIT_TEST_SMTP_PORT", "2525")

    app = a2kit.App("test")
    # No explicit `app.provide(_SmtpSettings)` — auto-resolution must kick in.

    async with app:
        settings = await app._resolver.get(_SmtpSettings)

    assert isinstance(settings, _SmtpSettings)
    assert settings.host == "envhost"
    assert settings.port == 2525


@pytest.mark.asyncio
async def test_non_basesettings_zero_arg_class_not_auto_resolved() -> None:
    """A non-``BaseSettings`` zero-arg-constructible class is NOT auto-resolved."""
    from a2kit.packages.di.container import UnresolvableType

    app = a2kit.App("test")

    async with app:
        with pytest.raises(UnresolvableType):
            await app._resolver.get(_NotSettings)


def test_container_does_not_import_pydantic() -> None:
    """The DI container module duck-types ``BaseSettings``; it MUST NOT import pydantic.

    Spec contract: auto-resolution detection uses inheritance walk + duck-typing
    so the container is usable without pydantic-settings installed.
    """
    import a2kit.packages.di.container as container_module

    source = container_module.__file__
    assert source is not None
    with open(source, encoding="utf-8") as f:
        text = f.read()

    forbidden = ("import pydantic", "from pydantic")
    found = [needle for needle in forbidden if needle in text]
    assert not found, (
        f"container.py imports pydantic ({found}) — must use duck-typing per spec"
    )
