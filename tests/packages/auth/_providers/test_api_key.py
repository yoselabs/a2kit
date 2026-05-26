"""Unit tests for the api_key manifest factory."""

from __future__ import annotations

from a2kit.packages._plugin import PluginManifest, Unavailable
from a2kit.packages.auth._providers.api_key import MANIFEST, _factory
from a2kit.packages.auth.api_key import APIKeyAuth, ApiKey


def test_manifest_declares_apikeyauth_protocol() -> None:
    assert isinstance(MANIFEST, PluginManifest)
    assert MANIFEST.name == "api_key"
    assert MANIFEST.protocol is APIKeyAuth


def test_factory_returns_unavailable_when_context_is_none() -> None:
    result = _factory(None)
    assert isinstance(result, Unavailable)
    assert "no api keys" in result.reason


def test_factory_returns_unavailable_when_iterable_is_empty() -> None:
    result = _factory(())
    assert isinstance(result, Unavailable)


def test_factory_returns_apikeyauth_for_iterable_of_keys() -> None:
    keys = [ApiKey(value="k1", subject="alice")]
    result = _factory(keys)
    assert isinstance(result, APIKeyAuth)
    assert not callable(result.keys)
    assert tuple(result.keys) == tuple(keys)


def test_factory_returns_apikeyauth_for_callable_context() -> None:
    def _keys() -> tuple[ApiKey, ...]:
        return (ApiKey(value="k1", subject="alice"),)

    result = _factory(_keys)
    assert isinstance(result, APIKeyAuth)


def test_factory_returns_unavailable_for_unsupported_type() -> None:
    result = _factory(123)
    assert isinstance(result, Unavailable)
    assert "unsupported" in result.reason
