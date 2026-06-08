"""Flat canonical names slug_leaf + canonical_name_override (ADR 0028 Wave 2)."""

from __future__ import annotations

import pytest

import a2kit
from a2kit._surfaces import resolve_canonical_name


def test_resolver_precedence() -> None:
    # override wins verbatim (slug never re-applied)
    assert resolve_canonical_name("jira_search", "jira", "search") == "jira_search"
    # router verb → slug_leaf
    assert resolve_canonical_name(None, "entity", "update") == "entity_update"
    # app-level → bare leaf
    assert resolve_canonical_name(None, None, "health") == "health"


def test_router_verb_canonical_is_slug_leaf() -> None:
    class Entity(a2kit.Router):
        slug = "entity"

        @a2kit.read()
        async def update(self, *, id: str) -> dict:
            return {"id": id}

    app = a2kit.App("k").add_router(Entity())
    names = {d.name for d in app.tools()}
    assert names == {"entity_update"}


def test_canonical_name_override_is_verbatim() -> None:
    class Jira(a2kit.Router):
        slug = "jira"

        @a2kit.read(canonical_name_override="jira_search")
        async def search(self, *, q: str) -> dict:
            return {"q": q}

        @a2kit.read()
        async def issues(self) -> dict:
            return {}

    app = a2kit.App("k").add_router(Jira())
    names = {d.name for d in app.tools()}
    # pin stays verbatim (no jira_jira_search); sibling auto-derives.
    assert names == {"jira_search", "jira_issues"}


@pytest.mark.asyncio
async def test_canonical_name_on_mcp_and_http() -> None:
    from a2kit.packages.http import build_http_app
    from a2kit.packages.mcp.server import build_mcp_server
    from a2kit.runtime import build

    class Entity(a2kit.Router):
        slug = "entity"

        @a2kit.read()
        async def update(self, *, id: str = "") -> dict:
            return {"id": id}

    app = a2kit.App("k").add_router(Entity())

    server = build_mcp_server(app, code_mode=False)
    mcp_names = {t.name for t in await server.list_tools()}
    assert "entity_update" in mcp_names
    assert "update" not in mcp_names

    runtime = build(app)
    async with runtime:
        api = build_http_app(runtime)
        mounted = {getattr(r, "path", None) for r in api.routes}
        assert "/entity_update" in mounted
        assert "/update" not in mounted
