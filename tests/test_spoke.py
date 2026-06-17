"""Mirror: the ``a2kit.spoke`` facade re-exports the packages.spoke surface."""

from __future__ import annotations


def test_facade_reexports_client_surface() -> None:
    from a2kit import spoke
    from a2kit.packages.spoke import SpokeClient, SpokeError, client

    assert spoke.client is client
    assert spoke.SpokeClient is SpokeClient
    assert spoke.SpokeError is SpokeError
    assert set(spoke.__all__) == {"SpokeClient", "SpokeError", "client"}
