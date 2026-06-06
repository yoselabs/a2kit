"""Fixture router for the HTTP DI-override visibility test.

Deliberately WITHOUT `from __future__ import annotations`: the
`dependency_overrides` wiring resolves real annotation objects, so the
leak it guards against only reproduces when annotations are concrete
types (not PEP 563 strings). Keeping this in its own non-future module
makes the RED test faithful to a real downstream app.
"""

from typing import Any

import a2kit


class Vault:
    tag = "vault"


class VaultRouter(a2kit.Router):
    slug = "ops"

    @a2kit.write(visibility="cli")
    async def trust_vault(self, *, path: str, vault: Vault) -> dict[str, Any]:
        return {"path": path, "tag": vault.tag}

    tools = (trust_vault,)
