"""Composition root for the remote-MCP-access example.

Two entry points:

- `build_cli_app()` returns an a2kit.App wired for CLI use — no auth,
  identity is `$USER@local` via a fallback UserSession factory.

- `build_mcp_app()` + `build_server()` returns a FastMCP server
  configured per ADR 0011 (GoogleProvider + Fernet-wrapped filesystem
  token store + jwt_signing_key + StaticTokenVerifier escape hatch +
  Streamable HTTP). The MCP composition root registers
  `build_user_session` as the per-call factory; email comes from the
  verified Google JWT.

The router and verbs in `routers.py` are transport-clean per
ADR 0010 — only this file differs between CLI and MCP modes.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import a2kit

from .routers import NotesRouter
from .session import (
    UserSession,
    build_cli_user_session,
    build_user_session,
)


class _GoogleAuthApp(a2kit.App):
    name = "mcp-google-auth-example"
    routers = (NotesRouter,)


def build_cli_app() -> a2kit.App:
    """CLI composition root — no auth, identity from $USER."""
    app = _GoogleAuthApp()
    app.provide(UserSession, build_cli_user_session, per_call=True)
    return app


def build_mcp_app() -> a2kit.App:
    """MCP composition root — identity from verified Google JWT."""
    app = _GoogleAuthApp()
    app.provide(UserSession, build_user_session, per_call=True)
    return app


def _build_auth() -> Any:
    """Construct the FastMCP auth layer per ADR 0011's recipe.

    Returns a StaticTokenVerifier when STATIC_TOKENS_JSON is set and
    Google credentials are absent — the bearer-only mode used by the
    CI smoke test and DCR-incompatible clients.

    Returns a GoogleProvider otherwise.

    Loud failure on missing required env vars per AGENTS.md
    principle 3.
    """
    from fastmcp.server.auth import StaticTokenVerifier

    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
    static_tokens_json = os.environ.get("STATIC_TOKENS_JSON")
    jwt_signing_key = os.environ.get("JWT_SIGNING_KEY")
    base_url = os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000")
    fernet_key = os.environ.get("FERNET_KEY")
    token_cache_path = os.environ.get(
        "TOKEN_CACHE_PATH",
        str(Path("~/.local/share/mcp-google-auth-example/oauth-cache").expanduser()),
    )

    # Bearer-only mode (smoke test, or DCR-incompatible clients).
    if static_tokens_json and not client_id:
        tokens = json.loads(static_tokens_json)
        return StaticTokenVerifier(tokens=tokens)

    if not (client_id and client_secret and jwt_signing_key and fernet_key):
        raise RuntimeError(
            "Missing required env vars for Google auth. Either set "
            "GOOGLE_CLIENT_ID + GOOGLE_CLIENT_SECRET + JWT_SIGNING_KEY + "
            "FERNET_KEY (production), or set STATIC_TOKENS_JSON alone "
            "(bearer-only mode). See .env.example."
        )

    # Google-mode imports are deferred so bearer-only mode (smoke test,
    # CI) does not require py-key-value-aio[disk] or cryptography.
    from cryptography.fernet import Fernet
    from fastmcp.server.auth.providers.google import GoogleProvider
    from key_value.aio.stores.disk import DiskStore
    from key_value.aio.wrappers.encryption import FernetEncryptionWrapper

    storage = FernetEncryptionWrapper(
        key_value=DiskStore(directory=token_cache_path),
        fernet=Fernet(fernet_key.encode()),
    )
    return GoogleProvider(
        client_id=client_id,
        client_secret=client_secret,
        base_url=base_url,
        client_storage=storage,
        jwt_signing_key=jwt_signing_key,
        required_scopes=["openid", "email"],
    )


def build_server() -> Any:
    """Build the FastMCP server with the ADR 0011 auth recipe."""
    from a2kit.packages.mcp.server import build_mcp_server

    app = build_mcp_app()
    auth = _build_auth()
    return build_mcp_server(app, auth=auth)


def main() -> None:
    """CLI entry point. MCP serving is via `build_server()` + a runner."""
    a2kit.run(build_cli_app())


if __name__ == "__main__":
    main()
