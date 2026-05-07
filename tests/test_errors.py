"""Tests for a2kit.errors — ErrorEnricher protocol, registry, and built-in."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from a2kit import (
    ConnectionNotFound,
    ConnectionNotFoundEnricher,
    EnricherRegistry,
    ErrorEnricher,
)

if TYPE_CHECKING:
    from pathlib import Path

    from a2kit import ConnectionStore

    from .conftest import AtlassianInfo


def test_protocol_runtime_check_accepts_compatible_class() -> None:
    class _MyEnricher:
        def enrich(self, exc: Exception, *, tool_name: str | None = None) -> Exception:
            return exc

    assert isinstance(_MyEnricher(), ErrorEnricher)


def test_registry_returns_input_when_empty() -> None:
    reg = EnricherRegistry()
    exc = ValueError("x")
    assert reg.enrich(exc) is exc


def test_registry_first_matching_enricher_wins() -> None:
    class _A:
        def enrich(self, exc: Exception, *, tool_name: str | None = None) -> Exception:
            if isinstance(exc, ValueError):
                return RuntimeError("from A")
            return exc

    class _B:
        def enrich(self, exc: Exception, *, tool_name: str | None = None) -> Exception:
            return RuntimeError("from B")  # would always fire

    reg = EnricherRegistry()
    reg.register(_A())
    reg.register(_B())

    out = reg.enrich(ValueError("v"))
    assert isinstance(out, RuntimeError)
    assert "from A" in str(out)


def test_registry_falls_through_when_first_returns_input(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Pass:
        def enrich(self, exc: Exception, *, tool_name: str | None = None) -> Exception:
            return exc

    class _Wins:
        def enrich(self, exc: Exception, *, tool_name: str | None = None) -> Exception:
            return RuntimeError(f"wins:{tool_name}")

    reg = EnricherRegistry()
    reg.register(_Pass())
    reg.register(_Wins())

    out = reg.enrich(ValueError("v"), tool_name="my_tool")
    assert "wins:my_tool" in str(out)


def test_connection_not_found_enricher_passes_through_other_exceptions(
    atlassian_store: ConnectionStore[AtlassianInfo],
) -> None:
    enricher = ConnectionNotFoundEnricher(atlassian_store)
    exc = ValueError("nope")
    assert enricher.enrich(exc) is exc


def test_connection_not_found_enricher_adds_available_list_and_suggestion(
    atlassian_store: ConnectionStore[AtlassianInfo], config_dir: Path
) -> None:
    from .conftest import AtlassianInfo

    atlassian_store.save(AtlassianInfo(key=("prod",), url="https://x", email="e", token="t"))
    atlassian_store.save(AtlassianInfo(key=("staging",), url="https://x", email="e", token="t"))

    enricher = ConnectionNotFoundEnricher(atlassian_store)
    out = enricher.enrich(ConnectionNotFound(("proteea",)), tool_name="my_tool")

    assert isinstance(out, ConnectionNotFound)
    assert "Available" in str(out)
    assert "prod" in str(out)
    assert "my_tool" in str(out)
    assert out.available_connections == ["prod", "staging"]


def test_connection_not_found_enricher_handles_empty_store(
    atlassian_store: ConnectionStore[AtlassianInfo],
) -> None:
    enricher = ConnectionNotFoundEnricher(atlassian_store)
    out = enricher.enrich(ConnectionNotFound(("missing",)))
    assert "No connections" in str(out)


def test_connection_not_found_enricher_no_close_match(
    atlassian_store: ConnectionStore[AtlassianInfo],
) -> None:
    from .conftest import AtlassianInfo

    atlassian_store.save(AtlassianInfo(key=("alpha",), url="https://x", email="e", token="t"))
    enricher = ConnectionNotFoundEnricher(atlassian_store)
    out = enricher.enrich(ConnectionNotFound(("zzzzzzzz",)))
    msg = str(out)
    assert "Available" in msg
    assert "Did you mean" not in msg
