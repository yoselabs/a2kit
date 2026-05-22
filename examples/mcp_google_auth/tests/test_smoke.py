"""Smoke test for the remote-MCP-access pattern.

What this catches:

1. Workspace dir hashing contract (spec scenario "workspace dir name
   is opaque"): the directory name is exactly 16 hex chars, raw email
   does not appear in the path, `_email` forensics file is written.
2. Per-user write isolation (spec scenario "per-user write isolation
   holds"): two fixture users see distinct workspaces; writes under
   one are invisible to the other.
3. Verb wiring through a2kit's MCP transport (in-process FastMCP):
   the three verbs are reachable, the per-call DI factory binds
   `UserSession`, and the return shapes match the spec.
4. Auth wiring shape: `_build_auth()` produces a StaticTokenVerifier
   in bearer-only mode — exercises the recipe code path under test
   without driving the interactive Google OAuth leg.

What this does NOT catch:

- Interactive Google OAuth flow (out of scope per ADR 0011 — that
  path is FastMCP's responsibility and has upstream coverage).
- Token refresh semantics (same).
- HTTP transport edge cases (the in-process MCP transport bypasses
  the wire). Real-transport coverage of auth is a future task.

Runs in well under 10 seconds, no network sockets.
"""

from __future__ import annotations

import asyncio
import re
import time
from pathlib import Path

import pytest

from a2kit.testing import client

from examples.mcp_google_auth.session import (
    UserSession,
    _workspace_dir_for,
)


# ---------------------------------------------------------------------- #
# 1. Workspace-dir hashing contract
# ---------------------------------------------------------------------- #


def test_workspace_dir_name_is_opaque_16_hex(tmp_path: Path) -> None:
    """Spec: workspace dir basename is exactly 16 hex characters; the
    raw email never appears in the path."""
    email = "alice@example.com"
    ws = _workspace_dir_for(email, tmp_path)

    assert ws.name == "ec5e645a4321b1e0"[:16] or re.fullmatch(r"[0-9a-f]{16}", ws.name)
    assert email not in str(ws), f"raw email leaked into workspace path: {ws}"
    assert ws.exists()


def test_workspace_writes_email_forensics_file(tmp_path: Path) -> None:
    """Spec: `_email` file inside the workspace contains the raw email
    for forensics."""
    email = "alice@example.com"
    ws = _workspace_dir_for(email, tmp_path)

    forensics = ws / "_email"
    assert forensics.exists()
    assert forensics.read_text() == email


def test_workspace_dirs_distinct_per_user(tmp_path: Path) -> None:
    """Spec: two users get different workspace dirs, neither is a
    prefix of the other."""
    ws_a = _workspace_dir_for("alice@example.com", tmp_path)
    ws_b = _workspace_dir_for("bob@example.com", tmp_path)

    assert ws_a != ws_b
    assert not str(ws_a).startswith(str(ws_b))
    assert not str(ws_b).startswith(str(ws_a))


def test_workspace_dir_normalises_email_case(tmp_path: Path) -> None:
    """Hashing uses `email.lower().strip()`; case variants collapse."""
    ws_a = _workspace_dir_for("Alice@Example.com", tmp_path)
    ws_b = _workspace_dir_for("alice@example.com  ", tmp_path)

    assert ws_a == ws_b


# ---------------------------------------------------------------------- #
# 2. Per-user write isolation through the verbs
# ---------------------------------------------------------------------- #


def _build_app_with_fake_user(user: UserSession):
    """Build the example app but override UserSession to a fixed value.

    The MCP factory `build_user_session` reads from FastMCP's
    `get_access_token()`, which is not bound under the in-process
    test transport. Overriding via composition-root re-registration
    (ADR 0006) is the documented pattern for tests.
    """
    import a2kit

    from examples.mcp_google_auth.routers import NotesRouter

    return a2kit.App("mcp-google-auth-example").provide(UserSession, lambda: user, per_call=True).add_router(NotesRouter())


def test_per_user_write_isolation(tmp_path: Path) -> None:
    """Spec: a write under T1 is invisible to a read under T2."""
    alice = UserSession(
        email="alice@example.com",
        workspace_dir=_workspace_dir_for("alice@example.com", tmp_path),
    )
    bob = UserSession(
        email="bob@example.com",
        workspace_dir=_workspace_dir_for("bob@example.com", tmp_path),
    )

    async def run_alice_write_bob_read() -> tuple[dict, dict]:
        async with client(_build_app_with_fake_user(alice)) as c_alice:
            write_res = await c_alice.invoke("notes.note_write", key="k1", value="alice-secret")
        async with client(_build_app_with_fake_user(bob)) as c_bob:
            read_res = await c_bob.invoke("notes.note_read", key="k1")
        return write_res, read_res

    write_res, read_res = asyncio.run(run_alice_write_bob_read())

    assert write_res["email"] == "alice@example.com"
    # Bob's read sees no value — workspaces are isolated.
    assert read_res["email"] == "bob@example.com"
    assert read_res["value"] is None


def test_whoami_returns_authenticated_identity(tmp_path: Path) -> None:
    """Spec: whoami returns the email and workspace path."""
    alice = UserSession(
        email="alice@example.com",
        workspace_dir=_workspace_dir_for("alice@example.com", tmp_path),
    )

    async def go() -> dict:
        async with client(_build_app_with_fake_user(alice)) as c:
            return await c.invoke("notes.whoami")

    result = asyncio.run(go())
    assert result["email"] == "alice@example.com"
    assert re.fullmatch(r".*/[0-9a-f]{16}$", result["workspace_dir"])


def test_invalid_key_is_rejected_loudly(tmp_path: Path) -> None:
    """Key validator rejects path-traversal-shaped keys."""
    alice = UserSession(
        email="alice@example.com",
        workspace_dir=_workspace_dir_for("alice@example.com", tmp_path),
    )

    async def go() -> None:
        async with client(_build_app_with_fake_user(alice)) as c:
            await c.invoke("notes.note_write", key="../escape", value="x")

    with pytest.raises(Exception):
        asyncio.run(go())


# ---------------------------------------------------------------------- #
# 3. Auth wiring shape — bearer-only mode produces a StaticTokenVerifier
# ---------------------------------------------------------------------- #


def test_build_auth_bearer_only_mode(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Spec: setting STATIC_TOKENS_JSON without Google credentials
    selects the bearer-only escape hatch."""
    from fastmcp.server.auth import StaticTokenVerifier

    from examples.mcp_google_auth.server import _build_auth

    monkeypatch.setenv(
        "STATIC_TOKENS_JSON",
        '{"T1":{"client_id":"s","scopes":["email"],"claims":{"email":"alice@example.com"}}}',
    )
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))

    auth = _build_auth()
    assert isinstance(auth, StaticTokenVerifier)


def test_build_auth_loud_failure_on_missing_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Spec: missing required env vars fail loud (AGENTS.md principle 3),
    not silently."""
    from examples.mcp_google_auth.server import _build_auth

    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("STATIC_TOKENS_JSON", raising=False)
    monkeypatch.delenv("JWT_SIGNING_KEY", raising=False)
    monkeypatch.delenv("FERNET_KEY", raising=False)

    with pytest.raises(RuntimeError, match="Missing required env vars"):
        _build_auth()


# ---------------------------------------------------------------------- #
# 4. Smoke-test wall-clock budget
# ---------------------------------------------------------------------- #


def test_smoke_suite_completes_under_budget() -> None:
    """Per spec: smoke completes in under 10s. This test runs last
    and asserts the elapsed wall-clock from the module-import marker."""
    elapsed = time.monotonic() - _MODULE_LOAD
    assert elapsed < 10.0, f"smoke suite took {elapsed:.2f}s, budget is 10s"


_MODULE_LOAD = time.monotonic()
