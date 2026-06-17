"""README ↔ live-code parity gate (v0.33).

Parses ``README.md`` and asserts that every claimed public symbol resolves
on the live module surface. Catches doc drift at PR time rather than at
consumer-migration time.

Patterns checked (extracted from fenced code blocks and inline backtick spans):

- ``a2kit.X`` / ``@a2kit.X`` — must ``hasattr(a2kit, "X")``
- ``a2kit.<submodule>.X`` / ``@a2kit.<submodule>.X`` — module + attribute must resolve
- ``App.X`` / ``app.X`` — must ``hasattr(a2kit.App, "X")``
- ``Router.X`` — must ``hasattr(a2kit.Router, "X")``
- ``@app.X`` — must ``hasattr(a2kit.App, "X")``

False positives on prose mentions are tolerated (they're still valid claims
if the symbol exists). False negatives (symbol claimed in prose without
backticks) are tolerated for v0.33.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest

import a2kit
from a2kit.app import App

# Alias under a non-Test-prefixed name so pytest does not try to collect
# the framework's TestClient as a test class.
from a2kit.packages.testing.client import TestClient as _TestClient
from a2kit.routers import Router

README = Path(__file__).resolve().parent.parent / "README.md"


# Identifiers that look like Python attribute paths but are NOT a2kit symbols.
# Skip these to avoid noise on third-party API mentions and prose words.
_NON_A2KIT_PREFIXES: tuple[str, ...] = (
    "fastmcp.",
    "pydantic.",
    "asyncio.",
    "typing.",
    "click.",
    "typer.",
    "pytest.",
    "logging.",
    "contextlib.",
    "anyio.",
    "mcp.",
    "ctx.",  # ToolContext methods (forwarded from fastmcp.Context)
    "T.",  # generic type parameters
    "self.",
    "cls.",
    "fn.",
    "store.",  # examples reference a `store` instance, not a public a2kit symbol
)

# Names that appear in README but are NOT part of the public surface
# (e.g. example-only identifiers, generic placeholders).
_EXAMPLE_ONLY_NAMES: frozenset[str] = frozenset(
    {
        "TrackerConn",
        "TrackerStore",
        "ProjectsRouter",
        "TasksRouter",
        "ConnectionConfig",  # this IS public but lives in connections package
        "AppState",
        "AppSettings",
        "Pool",
        "SqliteResource",
        "SqliteSettings",
        "BrowserPool",
        "FetchResponse",
        "ImportComplete",
        "BatchReport",
        "MyEvent",
        "Task",
        "FlatTask",
        "ReportT",
        "MyReport",
        "SearchIndex",
        "Settings",
        "WebRouter",
        "SubmitBody",
        "Result",
        "Page",
        "Visibility",
        "ToolAnnotations",  # mcp.types
        "Container",  # internal DI
    }
)


_FENCED_BLOCK_RE = re.compile(r"```[a-zA-Z]*\n(.*?)```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")


def _extract_code_chunks(readme_text: str) -> list[tuple[str, int]]:
    """Yield (chunk, starting_line_number) for fenced blocks and inline spans."""
    chunks: list[tuple[str, int]] = []
    # Fenced blocks
    for m in _FENCED_BLOCK_RE.finditer(readme_text):
        start = m.start()
        line_no = readme_text.count("\n", 0, start) + 1
        chunks.append((m.group(1), line_no))
    # Inline spans
    for m in _INLINE_CODE_RE.finditer(readme_text):
        start = m.start()
        line_no = readme_text.count("\n", 0, start) + 1
        chunks.append((m.group(1), line_no))
    return chunks


# Patterns. Order matters: longest paths first.
_PATTERN_A2KIT_SUBMODULE = re.compile(r"@?a2kit\.([a-z_][a-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)")
_PATTERN_A2KIT_TOPLEVEL = re.compile(r"@?a2kit\.([A-Za-z_][A-Za-z0-9_]*)")
_PATTERN_APP = re.compile(r"(?:^|[^A-Za-z0-9_])@?(?:App|app)\.([A-Za-z_][A-Za-z0-9_]*)")
_PATTERN_ROUTER = re.compile(r"(?:^|[^A-Za-z0-9_])Router\.([A-Za-z_][A-Za-z0-9_]*)")
# canonical-api-drift-gate: catch ``client.X`` / ``c.X`` references where the
# variable is a TestClient instance. Method drift on the test client (rename,
# removal) shows up at README parse time rather than at consumer-migration
# time.
_PATTERN_TESTCLIENT = re.compile(r"(?:^|[^A-Za-z0-9_])(?:client|c)\.([A-Za-z_][A-Za-z0-9_]*)")
# Methods that may legitimately appear after ``client.`` / ``c.`` in README
# code blocks but are NOT on TestClient — e.g. ``self.client.aclose()`` where
# the local ``client`` is an ``httpx.AsyncClient``. We accept these as
# example-code idioms rather than canonical-API claims.
_TESTCLIENT_FALSE_POSITIVES: frozenset[str] = frozenset(
    {
        # httpx.AsyncClient methods (README examples have a local `client`
        # that is an httpx client, not a TestClient).
        "aclose",
        "get",
        "post",
        "put",
        "delete",
        "stream",
        # TestClient instance attrs set in __init__; resolvable on
        # instances but not via hasattr(class, attr).
        "events",
        "progress",
        "logs",
        "reports",
        "progress_with_message",
        "app",
    }
)


def _resolve_a2kit_attr(name: str) -> tuple[bool, str]:
    if name in _EXAMPLE_ONLY_NAMES:
        return True, ""
    if hasattr(a2kit, name):
        return True, ""
    return False, f"hasattr(a2kit, {name!r}) is False"


def _resolve_a2kit_submodule_attr(submod: str, name: str) -> tuple[bool, str]:
    # `name` may itself be another submodule (e.g. ``a2kit.packages.connections``).
    # Try as a submodule first, then as an attribute.
    try:
        importlib.import_module(f"a2kit.{submod}.{name}")
        return True, ""
    except ImportError:
        pass
    try:
        mod = importlib.import_module(f"a2kit.{submod}")
    except ImportError as e:
        return False, f"import a2kit.{submod} failed: {e}"
    if hasattr(mod, name):
        return True, ""
    return False, f"hasattr(a2kit.{submod}, {name!r}) is False"


def _resolve_app_attr(name: str) -> tuple[bool, str]:
    if name in _EXAMPLE_ONLY_NAMES:
        return True, ""
    if hasattr(App, name):
        return True, ""
    return False, f"hasattr(a2kit.App, {name!r}) is False"


def _resolve_router_attr(name: str) -> tuple[bool, str]:
    if name in _EXAMPLE_ONLY_NAMES:
        return True, ""
    if hasattr(Router, name):
        return True, ""
    return False, f"hasattr(a2kit.Router, {name!r}) is False"


def _resolve_testclient_attr(name: str) -> tuple[bool, str]:
    if name in _TESTCLIENT_FALSE_POSITIVES:
        return True, ""
    if hasattr(_TestClient, name):
        return True, ""
    return False, f"hasattr(TestClient, {name!r}) is False"


def _skip_chunk(chunk: str) -> bool:
    """Heuristic: skip chunks that don't look like Python code or API claims."""
    # Skip shell commands, URLs, env var snippets.
    return chunk.startswith(("$", "/", "http://", "https://"))


_SUBMODULE_NAMES: frozenset[str] = frozenset(
    {
        "log",
        "testing",
        "packages",
        "lifespan",
        "schema",
        "exceptions",
        "tool",
        "app",
        "routers",
        "metadata",
        "signature",
        "capabilities",
    }
)


def _drift_in_chunk(chunk: str, line_no: int) -> list[tuple[str, int, str]]:  # noqa: C901 -- pattern-by-pattern dispatch is the clear shape
    """Yield drift entries for one code chunk."""
    out: list[tuple[str, int, str]] = []
    for m in _PATTERN_A2KIT_SUBMODULE.finditer(chunk):
        submod, attr = m.group(1), m.group(2)
        ok, reason = _resolve_a2kit_submodule_attr(submod, attr)
        if not ok:
            out.append((f"a2kit.{submod}.{attr}", line_no, reason))

    chunk_for_toplevel = _PATTERN_A2KIT_SUBMODULE.sub("", chunk)
    for m in _PATTERN_A2KIT_TOPLEVEL.finditer(chunk_for_toplevel):
        attr = m.group(1)
        if attr in _SUBMODULE_NAMES:
            continue
        ok, reason = _resolve_a2kit_attr(attr)
        if not ok:
            out.append((f"a2kit.{attr}", line_no, reason))

    for m in _PATTERN_APP.finditer(chunk):
        attr = m.group(1)
        ok, reason = _resolve_app_attr(attr)
        if not ok:
            out.append((f"App.{attr}", line_no, reason))

    for m in _PATTERN_ROUTER.finditer(chunk):
        attr = m.group(1)
        ok, reason = _resolve_router_attr(attr)
        if not ok:
            out.append((f"Router.{attr}", line_no, reason))

    for m in _PATTERN_TESTCLIENT.finditer(chunk):
        attr = m.group(1)
        ok, reason = _resolve_testclient_attr(attr)
        if not ok:
            out.append((f"TestClient.{attr}", line_no, reason))

    return out


def _collect_drift(readme_text: str) -> list[tuple[str, int, str]]:
    """Return list of (symbol, line, reason) for unresolved README claims."""
    drift: list[tuple[str, int, str]] = []
    for chunk, line_no in _extract_code_chunks(readme_text):
        if _skip_chunk(chunk):
            continue
        drift.extend(_drift_in_chunk(chunk, line_no))

    # De-duplicate (symbol, line) pairs.
    seen: set[tuple[str, int]] = set()
    unique: list[tuple[str, int, str]] = []
    for sym, line, reason in drift:
        key = (sym, line)
        if key in seen:
            continue
        seen.add(key)
        unique.append((sym, line, reason))
    return unique


def test_readme_symbols_resolve_in_live_code() -> None:
    """Every public symbol claimed in README.md must resolve at runtime."""
    text = README.read_text(encoding="utf-8")
    drift = _collect_drift(text)
    if drift:
        lines = [f"  README.md:{line} — {sym}: {reason}" for sym, line, reason in drift]
        msg = (
            "README claims symbols that do not resolve on the live a2kit surface.\n"
            "Update README to match the code, or add the missing symbols:\n" + "\n".join(lines)
        )
        pytest.fail(msg)
