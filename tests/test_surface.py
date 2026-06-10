"""Mirror tests for the ``surfaces=`` decorator kwarg (replaces ``visibility``)."""

from __future__ import annotations

import a2kit
from a2kit.metadata import _get_meta
from a2kit.routers import Router


def test_default_decorator_surfaces_is_all_listed() -> None:
    """Without `surfaces=`, the decorator stamps LISTED on every surface."""

    @a2kit.read()
    async def f() -> dict[str, int]:
        return {"k": 1}

    meta = _get_meta(f)
    assert meta is not None
    assert meta.extras.surfaces == {"mcp": "listed", "api": "listed", "cli": "listed"}


def test_explicit_cli_preserved() -> None:
    @a2kit.read(surfaces=("cli",))
    async def f() -> dict[str, int]:
        return {"k": 1}

    meta = _get_meta(f)
    assert meta is not None
    assert meta.extras.surfaces == {"mcp": "absent", "api": "absent", "cli": "listed"}


def test_explicit_hidden_preserved() -> None:
    @a2kit.write(surfaces={"cli": "unlisted"})
    async def f() -> dict[str, int]:
        return {"k": 1}

    meta = _get_meta(f)
    assert meta is not None
    assert meta.extras.surfaces == {"mcp": "absent", "api": "absent", "cli": "unlisted"}


def test_list_decorator_carries_surfaces() -> None:
    @a2kit.list_(surfaces=("cli",))
    async def f() -> list[dict[str, int]]:
        return [{"k": 1}]

    meta = _get_meta(f)
    assert meta is not None
    assert meta.extras.surfaces == {"mcp": "absent", "api": "absent", "cli": "listed"}


def test_write_decorator_carries_surfaces() -> None:
    """v0.33: `@a2kit.tool` removed; same surface check now on `@write`."""

    @a2kit.write(surfaces={"cli": "unlisted"})
    async def f() -> dict[str, int]:
        return {"k": 1}

    meta = _get_meta(f)
    assert meta is not None
    assert meta.extras.surfaces == {"mcp": "absent", "api": "absent", "cli": "unlisted"}


def test_router_per_verb_cli_surface() -> None:
    """Each verb in a router pins its own `surfaces=`."""

    class _R(Router):
        slug = "r"

        @a2kit.read(surfaces=("cli",))
        async def ping(self) -> dict[str, int]:
            return {"k": 1}

    router = _R()
    fn = router.bound_tools()[0]
    meta = _get_meta(fn)
    assert meta is not None
    assert meta.extras.surfaces == {"mcp": "absent", "api": "absent", "cli": "listed"}


def test_per_verb_explicit_all_surfaces() -> None:
    """A verb omitting `surfaces=` is LISTED on every surface."""

    class _R(Router):
        slug = "r"

        @a2kit.read()
        async def public_status(self) -> dict[str, int]:
            return {"k": 1}

    router = _R()
    fn = router.bound_tools()[0]
    meta = _get_meta(fn)
    assert meta is not None
    assert meta.extras.surfaces == {"mcp": "listed", "api": "listed", "cli": "listed"}


def test_router_default_surfaces_all() -> None:
    """Router verb with no surfaces= defaults to LISTED everywhere."""

    class _R(Router):
        slug = "r"

        @a2kit.read()
        async def ping(self) -> dict[str, int]:
            return {"k": 1}

    router = _R()
    fn = router.bound_tools()[0]
    meta = _get_meta(fn)
    assert meta is not None
    assert meta.extras.surfaces == {"mcp": "listed", "api": "listed", "cli": "listed"}
