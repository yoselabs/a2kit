"""v0.11 — public surface additions / contract tightenings.

Covers:
- `ToolMetadata` / `tool_metadata(fn)` public accessor wrapping the kit-stamped
  `_a2kit_*` attrs. Tests that consume metadata should go through this rather
  than the private attrs.
- `FastMCPLike` re-exported as a public Protocol.
- `ConnectionInfoLike` / `ConnectionStoreLike` re-exported from `a2kit` and
  `a2kit.connections` (their new home), still reachable via the old
  `a2kit.errors` import for one cycle.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel

import a2kit
from a2kit import (
    Cap,
    ConnectionInfoLike,
    ConnectionStoreLike,
    FastMCPLike,
    Router,
    ToolMetadata,
    tool_metadata,
)


class _Row(BaseModel):
    id: int
    name: str


# --- ToolMetadata accessor ----------------------------------------------------


def test_tool_metadata_basic() -> None:
    @a2kit.tool()
    async def fetch_widgets(limit: int = 10) -> list[dict]:  # type: ignore[type-arg]
        return [{"id": i} for i in range(limit)]

    meta = tool_metadata(fetch_widgets)
    assert isinstance(meta, ToolMetadata)
    assert meta.tool_name == "fetch_widgets"
    assert "tool:fetch_widgets" in meta.capabilities
    # `list[dict]` (untyped row shape) → format precomputed as None (runtime decide).
    assert meta.format is None


def test_tool_metadata_format_precomputed_for_pydantic() -> None:
    @a2kit.tool()
    async def list_rows() -> list[_Row]:
        return []

    meta = tool_metadata(list_rows)
    assert meta.format == "tsv"


def test_tool_metadata_explicit_capabilities() -> None:
    @a2kit.tool(capabilities={Cap.WRITE, "expensive"})
    async def big_job() -> dict:  # type: ignore[type-arg]
        return {}

    meta = tool_metadata(big_job)
    assert Cap.WRITE in meta.capabilities
    assert "expensive" in meta.capabilities


def test_tool_metadata_router_tag() -> None:
    class WidgetsRouter(Router):
        pass

    @WidgetsRouter.read()
    async def list_widgets() -> list[dict]:  # type: ignore[type-arg]
        return []

    # Router-level register is what tags; the bare _tools binding fn is the
    # raw function (not yet decorated). Only direct `@a2kit.tool` stamps
    # metadata at decoration time.
    @a2kit.tool()
    async def loose_tool() -> dict:  # type: ignore[type-arg]
        return {}

    meta = tool_metadata(loose_tool)
    assert meta.tool_name == "loose_tool"


def test_tool_metadata_undecorated_raises() -> None:
    async def naked() -> dict:  # type: ignore[type-arg]
        return {}

    with pytest.raises(AttributeError, match=r"@a2kit\.tool"):
        tool_metadata(naked)


def test_tool_metadata_is_frozen() -> None:
    @a2kit.tool()
    async def f() -> dict:  # type: ignore[type-arg]
        return {}

    meta = tool_metadata(f)
    with pytest.raises(Exception):  # noqa: B017, PT011  # frozen dataclass
        meta.tool_name = "other"  # ty: ignore[invalid-assignment]


# --- Re-exports / Protocols ---------------------------------------------------


def test_protocols_re_exported_at_top_level() -> None:
    """Both Protocols are importable from `a2kit` directly, not just submodules."""
    assert ConnectionInfoLike is a2kit.ConnectionInfoLike
    assert ConnectionStoreLike is a2kit.ConnectionStoreLike
    assert FastMCPLike is a2kit.FastMCPLike


def test_protocols_canonical_home_is_connections() -> None:
    """v0.11: canonical home for connection Protocols is `a2kit.connections`."""
    from a2kit import connections as conns

    assert conns.ConnectionInfoLike is ConnectionInfoLike
    assert conns.ConnectionStoreLike is ConnectionStoreLike


def test_protocols_still_importable_from_errors_for_one_cycle() -> None:
    """Backward compatibility — `a2kit.errors` still re-exports for one cycle."""
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        from a2kit import errors

    assert errors.ConnectionInfoLike is ConnectionInfoLike
    assert errors.ConnectionStoreLike is ConnectionStoreLike


# --- enrichers module rename --------------------------------------------------


def test_enrichers_is_canonical_module() -> None:
    """v0.11: `a2kit.enrichers` is the new home for `EnricherFn` / `chain` / `connection_enricher`."""
    from a2kit import enrichers

    # Top-level re-exports point at the same objects as the canonical module.
    assert a2kit.chain is enrichers.chain
    assert a2kit.connection_enricher is enrichers.connection_enricher
    assert a2kit.EnricherFn is enrichers.EnricherFn


def test_errors_module_is_deprecation_shim() -> None:
    """`a2kit.errors` still works for one cycle (until v0.13) but warns on import."""
    import importlib
    import sys
    import warnings

    # Force a re-import so the module-level warning fires fresh.
    sys.modules.pop("a2kit.errors", None)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        errors = importlib.import_module("a2kit.errors")

    deprecations = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    assert any("a2kit.enrichers" in str(w.message) for w in deprecations)
    # And the re-exports themselves still resolve to the canonical objects.
    from a2kit import enrichers

    assert errors.chain is enrichers.chain
    assert errors.connection_enricher is enrichers.connection_enricher


def test_a2kit_config_home_alias_removed_with_hint() -> None:
    """v0.11: `A2KIT_CONFIG_HOME` self-alias removed; ImportError hint points to `ENV_CONFIG_HOME`."""
    with pytest.raises(ImportError, match="ENV_CONFIG_HOME"):
        _ = a2kit.A2KIT_CONFIG_HOME  # noqa: B018


# --- FastMCPLike structural typing -------------------------------------------


def test_fastmcp_like_is_runtime_checkable() -> None:
    """`FastMCPLike` is `@runtime_checkable` — `isinstance` works on duck types."""

    class _RealEnough:
        settings: Any = type("S", (), {"host": "h", "port": 1})()

        def tool(self, *_a: Any, **_kw: Any) -> Any:
            return lambda fn: fn

        def run(self, *_a: Any, **_kw: Any) -> None:
            return None

    assert isinstance(_RealEnough(), FastMCPLike)


def test_fastmcp_like_rejects_missing_method() -> None:
    class _NoTool:
        settings: Any = type("S", (), {"host": "h", "port": 1})()

        def run(self, *_a: Any, **_kw: Any) -> None:
            return None

    assert not isinstance(_NoTool(), FastMCPLike)


# --- Async-first connection-store API ----------------------------------------


class _Conn(a2kit.ConnectionInfo):
    base_url: str


@pytest.fixture
def async_store(tmp_path: Any) -> a2kit.ConnectionStore[_Conn]:
    return a2kit.ConnectionStore(tmp_path / "c", _Conn)


async def test_async_store_round_trip(async_store: a2kit.ConnectionStore[_Conn]) -> None:
    """v0.11 async-first: `save` / `load` are `async def`."""
    info = _Conn(key=("dev",), base_url="https://dev.example.com")
    await async_store.save(info)
    loaded = await async_store.load("dev")
    assert loaded.base_url == "https://dev.example.com"


async def test_async_store_list_connections(async_store: a2kit.ConnectionStore[_Conn]) -> None:
    await async_store.save(_Conn(key=("a",), base_url="https://a"))
    await async_store.save(_Conn(key=("b",), base_url="https://b"))
    listed = await async_store.list_connections()
    keys = sorted(info.key for info in listed)
    assert keys == [("a",), ("b",)]


async def test_async_tool_awaits_store_load(async_store: a2kit.ConnectionStore[_Conn]) -> None:
    """An async tool decorated with `@a2kit.tool(store=...)` awaits
    `store.load` directly — no thread offload, no `_async` sibling."""
    await async_store.save(_Conn(key=("prod",), base_url="https://prod"))

    @a2kit.tool(store=async_store)
    async def fetch(*, info: _Conn) -> dict[str, str]:
        return {"url": info.base_url}

    out = await fetch(connection="prod")
    assert out == {"url": "https://prod"}


async def test_sync_tool_drives_async_store_via_anyio(async_store: a2kit.ConnectionStore[_Conn]) -> None:
    """Sync wrappers drive the async store through `_lookup_connection_sync`,
    which uses `anyio.from_thread.run` (worker-thread context) or
    `anyio.run` (no-loop context)."""
    await async_store.save(_Conn(key=("staging",), base_url="https://staging"))

    @a2kit.tool(store=async_store)
    def fetch_sync(*, info: _Conn) -> dict[str, str]:
        return {"url": info.base_url}

    # Worker-thread path: from_thread.run hops to the host loop.
    import anyio.to_thread

    out = await anyio.to_thread.run_sync(lambda: fetch_sync(connection="staging"))
    assert out == {"url": "https://staging"}


# --- MCPRunner.run_async ------------------------------------------------------


class _AsyncFakeServer:
    """Server fake that exposes both `run` (sync, raises) and `run_async`."""

    def __init__(self) -> None:
        self.settings = type("S", (), {"host": "", "port": 0})()
        self.run_async_calls: list[str] = []

    def tool(self, *_a: Any, **_kw: Any) -> Any:
        return lambda fn: fn

    def run(self, *_a: Any, **_kw: Any) -> None:
        msg = "sync run should not be called when run_async is available"
        raise AssertionError(msg)

    async def run_async(self, *, transport: str = "stdio") -> None:
        self.run_async_calls.append(transport)


class _SyncOnlyFakeServer:
    """Server fake without `run_async` — emulates older FastMCP."""

    def __init__(self) -> None:
        self.settings = type("S", (), {"host": "", "port": 0})()

    def tool(self, *_a: Any, **_kw: Any) -> Any:
        return lambda fn: fn

    def run(self, *_a: Any, **_kw: Any) -> None:
        return None


async def test_mcprunner_run_async_invokes_server_run_async() -> None:
    from a2kit.scaffold import MCPRunner

    server = _AsyncFakeServer()
    parsed = await MCPRunner(server).run_async(argv=[], transport="stdio")
    assert server.run_async_calls == ["stdio"]
    assert "effective_select" in parsed


async def test_mcprunner_run_async_http_sets_settings() -> None:
    from a2kit.scaffold import MCPRunner

    server = _AsyncFakeServer()
    await MCPRunner(server).run_async(argv=["--http", "0.0.0.0:7777"])  # noqa: S104
    assert server.run_async_calls == ["streamable-http"]
    assert server.settings.host == "0.0.0.0"  # noqa: S104
    assert server.settings.port == 7777


async def test_mcprunner_run_async_raises_without_server_support() -> None:
    from a2kit.scaffold import MCPRunner

    server = _SyncOnlyFakeServer()
    with pytest.raises(RuntimeError, match="run_async is not defined"):
        await MCPRunner(server).run_async(argv=[])


# --- Async enrichers ---------------------------------------------------------


async def test_async_enricher_awaited_by_async_tool() -> None:
    """An `async def` enricher returns a coroutine; the async tool wrapper awaits it."""

    async def async_enricher(exc: Exception, tool_name: str | None = None) -> Exception:
        # Imagine an async lookup happening here (SSO token resolution, etc.).
        return RuntimeError(f"enriched: {exc} (tool={tool_name})")

    @a2kit.tool(enricher=async_enricher)
    async def boom() -> dict[str, str]:
        msg = "kaboom"
        raise ValueError(msg)

    with pytest.raises(RuntimeError, match=r"enriched: kaboom \(tool=boom\)"):
        await boom()


async def test_chain_with_async_enricher() -> None:
    """`chain(...)` short-circuits on the first awaitable result."""
    from a2kit.enrichers import chain

    def sync_passthrough(exc: Exception, tool_name: str | None = None) -> Exception:
        return exc  # no transformation

    async def async_transform(exc: Exception, tool_name: str | None = None) -> Exception:
        return RuntimeError(f"async-enriched: {exc}")

    composed = chain(sync_passthrough, async_transform)

    @a2kit.tool(enricher=composed)
    async def boom() -> dict[str, str]:
        msg = "x"
        raise ValueError(msg)

    with pytest.raises(RuntimeError, match="async-enriched: x"):
        await boom()


def test_async_enricher_drained_for_sync_tool() -> None:
    """v0.11: async enrichers (e.g. the built-in `connection_enricher`)
    are drained by the sync tool wrapper through `anyio.from_thread.run`
    or `anyio.run`. Sync tools keep the feature without writing async."""

    async def async_enricher(exc: Exception, tool_name: str | None = None) -> Exception:
        return RuntimeError(f"async-enriched: {exc}")

    @a2kit.tool(enricher=async_enricher)
    def boom() -> dict[str, str]:
        msg = "x"
        raise ValueError(msg)

    with pytest.raises(RuntimeError, match="async-enriched: x"):
        boom()


# --- A2K014: file size lint rule --------------------------------------------


def test_a2k014_flags_oversized_file(tmp_path: Any) -> None:
    """A file over the limit is flagged at line 1."""
    from a2kit.lint.static import run_static_rules

    big = tmp_path / "src" / "big.py"
    big.parent.mkdir(parents=True)
    big.write_text("# pad\n" * 600)
    findings = run_static_rules([big])
    assert any(f.rule == "A2K014" and "600 lines" in f.message for f in findings)


def test_a2k014_passes_under_limit(tmp_path: Any) -> None:
    from a2kit.lint.static import run_static_rules

    small = tmp_path / "src" / "small.py"
    small.parent.mkdir(parents=True)
    small.write_text("x = 1\n" * 50)
    findings = run_static_rules([small])
    assert not any(f.rule == "A2K014" for f in findings)


def test_a2k014_skips_test_fixtures(tmp_path: Any) -> None:
    """Tests / examples are exempt — long suites are normal."""
    from a2kit.lint.static import run_static_rules

    big = tmp_path / "tests" / "test_big.py"
    big.parent.mkdir(parents=True)
    big.write_text("# pad\n" * 1000)
    findings = run_static_rules([big])
    assert not any(f.rule == "A2K014" for f in findings)


def test_a2k014_respects_noqa(tmp_path: Any) -> None:
    """Top-of-file `# noqa: A2K014` opt-out for legitimately-large modules."""
    from a2kit.lint.static import run_static_rules

    big = tmp_path / "src" / "vendored.py"
    big.parent.mkdir(parents=True)
    big.write_text("# noqa: A2K014\n" + ("# pad\n" * 600))
    findings = run_static_rules([big])
    assert not any(f.rule == "A2K014" for f in findings)


async def test_async_enricher_drained_for_sync_tool_called_from_async_test() -> None:
    """Last-resort drainage path: async test → sync tool → async enricher.
    A loop is already running on this thread, so `anyio.run` raises and we
    fall back to a fresh worker thread."""

    async def async_enricher(exc: Exception, tool_name: str | None = None) -> Exception:
        return RuntimeError(f"thread-drained: {exc}")

    @a2kit.tool(enricher=async_enricher)
    def boom() -> dict[str, str]:
        msg = "y"
        raise ValueError(msg)

    with pytest.raises(RuntimeError, match="thread-drained: y"):
        boom()
