"""Capability: ``App.auth(APIKeyAuth(...))`` and manifest-driven discovery
produce structurally identical auth wiring.
"""

from __future__ import annotations

from a2kit.packages.auth import APIKeyAuth, discover_api_key_providers
from a2kit.packages.auth.api_key import ApiKey


def test_manifest_discovery_yields_apikeyauth_when_keys_present() -> None:
    keys = (ApiKey(value="k1", subject="alice"),)
    discovered = discover_api_key_providers(keys)
    assert "api_key" in discovered
    spec = discovered["api_key"]
    assert isinstance(spec, APIKeyAuth)
    # Same shape as the imperative form
    imperative = APIKeyAuth(keys=keys)
    assert not callable(spec.keys)
    assert not callable(imperative.keys)
    assert tuple(spec.keys) == tuple(imperative.keys)
    assert spec.header == imperative.header
    assert spec.target == imperative.target


def test_manifest_discovery_drops_provider_when_no_keys() -> None:
    discovered = discover_api_key_providers(context=())
    assert "api_key" not in discovered
    assert discovered == {}


def test_manifest_discovery_drops_provider_when_context_is_none() -> None:
    discovered = discover_api_key_providers(context=None)
    assert "api_key" not in discovered


def test_manifest_discovery_accepts_callable_context() -> None:
    def _keys() -> tuple[ApiKey, ...]:
        return (ApiKey(value="k1", subject="alice"),)

    discovered = discover_api_key_providers(_keys)
    assert "api_key" in discovered
    spec = discovered["api_key"]
    assert callable(spec.keys)
