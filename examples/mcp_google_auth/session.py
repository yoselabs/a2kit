"""Per-user session value object and its per-call DI factory.

The factory reads the authenticated user's email from the active
FastMCP request's access token (Google JWT claims) and produces a
UserSession scoped to that user. Verbs that need user context
declare `user: UserSession` and receive an instance via DI under
the per_call=True scope (ADR 0009).

Workspace directory naming uses sha256(email)[:16] — opaque on
disk, deterministic, stateless. The raw email is preserved in a
`_email` file inside the workspace for forensics, and on
UserSession.email for any verb that needs to log a human-readable
identifier.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class UserSession:
    """The authenticated identity + per-user workspace path.

    Constructed per call by `build_user_session` (MCP mode) or
    `build_cli_user_session` (CLI mode, ADR 0006 override).
    """

    email: str
    workspace_dir: Path


def _workspace_dir_for(email: str, workspace_root: Path) -> Path:
    """Compute the per-user workspace path and create it lazily.

    Directory name is the first 16 hex chars of sha256(normalized email).
    On first creation, writes a `_email` file with the raw email.
    """
    normalized = email.lower().strip()
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    workspace = workspace_root / digest
    if not workspace.exists():
        workspace.mkdir(parents=True, exist_ok=True)
        (workspace / "_email").write_text(normalized, encoding="utf-8")
    return workspace


def build_user_session() -> UserSession:
    """Per-call factory for MCP mode.

    Reads the authenticated email from the active FastMCP request's
    access token. Raises if no token is present (the FastMCP auth
    layer should have rejected the request before reaching here;
    seeing None means a wiring bug — fail loud per AGENTS.md
    principle 3).
    """
    from fastmcp.server.dependencies import get_access_token

    token = get_access_token()
    if token is None:
        raise RuntimeError(
            "build_user_session: no access token on the active request. "
            "This factory is registered as per_call=True on the MCP "
            "composition root; reaching here without auth indicates the "
            "FastMCP auth layer is not installed. Pass auth=... to "
            "build_mcp_server, or use the CLI factory in CLI mode."
        )
    email = token.claims.get("email")
    if not isinstance(email, str) or not email:
        raise RuntimeError(
            "build_user_session: access token has no `email` claim. "
            "GoogleProvider should request the `openid email` scopes; "
            "verify the required_scopes config on the provider."
        )
    return UserSession(
        email=email,
        workspace_dir=_workspace_dir_for(email, _workspace_root()),
    )


def build_cli_user_session() -> UserSession:
    """Per-call factory for CLI mode (ADR 0006 composition-root override).

    CLI has no auth (ADR 0010). The fallback identity comes from the
    local environment — `$USER@local` — so the CLI and MCP factories
    produce structurally identical UserSession objects without the
    CLI pretending to be authenticated.
    """
    user = os.environ.get("USER") or os.environ.get("USERNAME") or "local"
    email = f"{user}@local"
    return UserSession(
        email=email,
        workspace_dir=_workspace_dir_for(email, _workspace_root()),
    )


def _workspace_root() -> Path:
    root = os.environ.get("WORKSPACE_ROOT")
    if not root:
        raise RuntimeError(
            "WORKSPACE_ROOT env var is required. Set it to a writable directory; the example creates per-user subdirectories inside it."
        )
    return Path(root).expanduser().resolve()
