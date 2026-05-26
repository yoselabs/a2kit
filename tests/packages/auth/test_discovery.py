"""Unit tests for the auth discovery helpers."""

from __future__ import annotations

from a2kit.packages.auth import discover_api_key_providers
from a2kit.packages.auth.api_key import APIKeyAuth, ApiKey


def test_discover_api_key_providers_returns_dict_with_apikeyauth() -> None:
    keys = (ApiKey(value="k1", subject="alice"),)
    discovered = discover_api_key_providers(keys)
    assert isinstance(discovered, dict)
    assert isinstance(discovered["api_key"], APIKeyAuth)


def test_discover_api_key_providers_returns_empty_when_unavailable() -> None:
    assert discover_api_key_providers(None) == {}
