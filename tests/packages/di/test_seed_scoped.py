"""``Container.seed_scoped(type_, value)`` — explicit per-call SCOPED registration.

Locks the contract: child-only, last-write-wins, resolvable by type.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from a2kit.packages.di import Container


@dataclass(frozen=True)
class _Identity:
    name: str


async def test_seed_scoped_on_child_registers_provider() -> None:
    root = Container()
    async with root:
        child = root.child()
        child.seed_scoped(_Identity, _Identity("alice"))
        got = await child.get(_Identity)
    assert got == _Identity("alice")


async def test_seed_scoped_on_root_raises() -> None:
    root = Container()
    with pytest.raises(TypeError, match="requires a child container"):
        root.seed_scoped(_Identity, _Identity("alice"))


async def test_seed_scoped_last_write_wins() -> None:
    root = Container()
    async with root:
        child = root.child()
        child.seed_scoped(_Identity, _Identity("first"))
        child.seed_scoped(_Identity, _Identity("second"))
        got = await child.get(_Identity)
    assert got == _Identity("second")


async def test_seed_scoped_flows_to_resolve_params() -> None:
    """A factory declaring ``ident: _Identity`` resolves to the seeded instance."""
    root = Container()

    async def factory(*, ident: _Identity) -> dict:
        return {"name": ident.name}

    async with root:
        child = root.child()
        child.seed_scoped(_Identity, _Identity("bob"))
        resolved = await child.resolve_params(factory)
    assert resolved == {"ident": _Identity("bob")}


async def test_call_scope_does_not_implicitly_seed_from_wire_values() -> None:
    """Typed wire values without matching param names MUST NOT auto-register
    as SCOPED providers. This locks the removal of the implicit
    wire-by-type loop from ``call_scope``.
    """
    root = Container()

    async def fn(*, name: str) -> str:
        return name

    async with (
        root,
        root.call_scope(
            fn,
            {"name": "alice", "extra": _Identity("ghost")},
        ) as merged,
    ):
        # extra was not a fn param; it should not have leaked into merged
        assert merged == {"name": "alice"}
        assert "extra" not in merged
        # _Identity is also NOT registered on any reachable container —
        # we have no API to inspect the child after exit, so the
        # absence-of-leak assertion is implicit in: no factory could
        # resolve _Identity from this scope.
