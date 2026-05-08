"""Tests for a2kit.errors — callable enricher contract + chain + built-in factory."""

from __future__ import annotations

from typing import TYPE_CHECKING

from a2kit import ConnectionNotFound, chain, connection_enricher

if TYPE_CHECKING:
    from pathlib import Path

    from a2kit import ConnectionStore

    from .conftest import AtlassianInfo


# ---- chain() ---------------------------------------------------------------


def test_chain_empty_is_identity() -> None:
    chained = chain()
    exc = ValueError("x")
    assert chained(exc) is exc


def test_chain_first_transformer_wins() -> None:
    def a(exc: Exception, tool_name: str | None = None) -> Exception:
        if isinstance(exc, ValueError):
            return RuntimeError("from A")
        return exc

    def b(exc: Exception, tool_name: str | None = None) -> Exception:
        return RuntimeError("from B")  # would always fire if reached

    chained = chain(a, b)
    out = chained(ValueError("v"))
    assert isinstance(out, RuntimeError)
    assert "from A" in str(out)


def test_chain_falls_through_to_next() -> None:
    def passthrough(exc: Exception, tool_name: str | None = None) -> Exception:
        return exc

    def wins(exc: Exception, tool_name: str | None = None) -> Exception:
        return RuntimeError(f"wins:{tool_name}")

    chained = chain(passthrough, wins)
    out = chained(ValueError("v"), "my_tool")
    assert "wins:my_tool" in str(out)


def test_chain_returns_input_when_no_match() -> None:
    def never(exc: Exception, tool_name: str | None = None) -> Exception:
        return exc

    chained = chain(never, never)
    exc = ValueError("v")
    assert chained(exc) is exc


# ---- connection_enricher() factory ------------------------------------------


async def test_connection_enricher_passes_through_other_exceptions(
    atlassian_store: ConnectionStore[AtlassianInfo],
) -> None:
    enrich = connection_enricher(atlassian_store)
    exc = ValueError("nope")
    assert await enrich(exc) is exc


async def test_connection_enricher_adds_available_list_and_suggestion(
    atlassian_store: ConnectionStore[AtlassianInfo],
    config_dir: Path,
) -> None:
    from .conftest import AtlassianInfo

    await atlassian_store.save(AtlassianInfo(key=("prod",), url="https://x", email="e", token="t"))
    await atlassian_store.save(AtlassianInfo(key=("staging",), url="https://x", email="e", token="t"))

    enrich = connection_enricher(atlassian_store)
    out = await enrich(ConnectionNotFound(("proteea",)), "my_tool")

    assert isinstance(out, ConnectionNotFound)
    assert "Available" in str(out)
    assert "prod" in str(out)
    assert "my_tool" in str(out)
    assert out.available_connections == ["prod", "staging"]


async def test_connection_enricher_handles_empty_store(
    atlassian_store: ConnectionStore[AtlassianInfo],
) -> None:
    enrich = connection_enricher(atlassian_store)
    out = await enrich(ConnectionNotFound(("missing",)))
    assert "No connections" in str(out)


async def test_connection_enricher_no_close_match(
    atlassian_store: ConnectionStore[AtlassianInfo],
) -> None:
    from .conftest import AtlassianInfo

    await atlassian_store.save(AtlassianInfo(key=("alpha",), url="https://x", email="e", token="t"))
    enrich = connection_enricher(atlassian_store)
    out = await enrich(ConnectionNotFound(("zzzzzzzz",)))
    msg = str(out)
    assert "Available" in msg
    assert "Did you mean" not in msg
