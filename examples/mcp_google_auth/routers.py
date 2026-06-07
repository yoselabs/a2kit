"""Three verbs that exercise the per-user workspace contract.

- whoami: returns the authenticated email + workspace path.
- note_write: stores a key/value under the user's workspace.
- note_read: reads a key from the user's workspace (or None).

Per the liftability rubric (docs/patterns/remote-mcp-access.md):
all three are server-owned state operations and lift cleanly to
remote MCP. They never touch the caller's local filesystem.
"""

from __future__ import annotations

import re

import a2kit

from .session import UserSession

# Keys are constrained to a safe character set so they cannot escape
# the per-user workspace via path traversal. Reject anything else
# loudly per AGENTS.md principle 3.
_KEY_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def _key_path(user: UserSession, key: str):
    if not _KEY_PATTERN.fullmatch(key):
        raise ValueError(f"note key {key!r} is invalid; allowed: 1-64 chars of [a-zA-Z0-9_-]. Reject loudly to prevent path traversal.")
    return user.workspace_dir / f"{key}.txt"


class NotesRouter(a2kit.Router):
    slug = "notes"

    @a2kit.read()
    async def whoami(self, *, user: UserSession) -> dict[str, str]:
        """Identify the authenticated caller.

        Returns the email from the verified Google access token and
        the per-user workspace path the server has provisioned.
        """
        return {"email": user.email, "workspace_dir": str(user.workspace_dir)}

    @a2kit.write()
    async def note_write(self, *, key: str, value: str, user: UserSession) -> dict[str, str]:
        """Store `value` under `key` in the caller's per-user workspace.

        Two users writing the same key store separate values in separate
        workspaces.
        """
        path = _key_path(user, key)
        path.write_text(value, encoding="utf-8")
        return {"email": user.email, "key": key, "path": str(path)}

    @a2kit.read()
    async def note_read(self, *, key: str, user: UserSession) -> dict[str, str | None]:
        """Read `value` for `key` from the caller's per-user workspace.

        Returns `value=None` if the key has not been written by this
        user. Cross-user reads return None — workspaces are isolated.
        """
        path = _key_path(user, key)
        if not path.exists():
            return {"email": user.email, "key": key, "value": None}
        return {"email": user.email, "key": key, "value": path.read_text(encoding="utf-8")}
