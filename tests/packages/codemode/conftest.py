"""Shared fixtures for code-execution surface tests."""

from __future__ import annotations

import pytest

import a2kit


class GateRouter(a2kit.Router):
    """Tools spanning every capability-gate case."""

    slug = "gate"

    @a2kit.read()
    async def ping(self) -> dict[str, str]:
        """Non-destructive read."""
        return {"msg": "pong"}

    @a2kit.read(visibility="cli")
    async def cli_only(self) -> dict[str, str]:
        """CLI-tier read — never registered on the MCP surface."""
        return {"msg": "cli-secret"}

    @a2kit.write()
    async def wipe(self) -> dict[str, str]:
        """Destructive write — `@a2kit.write` defaults destructive."""
        return {"msg": "wiped"}

    @a2kit.write(destructive=False)
    async def touch(self) -> dict[str, str]:
        """Non-destructive write."""
        return {"msg": "touched"}

    tools = (ping, cli_only, wipe, touch)


@pytest.fixture
def gate_app() -> a2kit.App:
    """Fresh App with the gate router for each test."""
    return a2kit.App("codemode-gate-test").add_router(GateRouter())
