"""validate-composition (ADR 0028 Wave 3) — the runtime canonical-name backstop.

``validate_composition(app)`` resolves the surfaces matrix + the canonical name
for every verb through the one shared ``resolve_canonical_name`` resolver and
asserts GLOBAL canonical-name uniqueness, failing loud with the offending
pair — WITHOUT a full surface build (no container seal, no transport). It is
layer 2 (the runtime backstop) of ADR 0028 decision 6; the static dup-name
lint rule (layer 1) consumes the same resolver in the orthogonal
``ruff-compatible-lint-codes`` change.

Additive, non-breaking: a uniquely-named App sees no behaviour change; an App
with a latent duplicate now fails loud at ``validate_composition`` / ``build``.
"""

from __future__ import annotations

import pytest

import a2kit
from a2kit.testing import app_of

# --------------------------------------------------------------------------- #
# Probe routers.
# --------------------------------------------------------------------------- #


def _colliding_app() -> a2kit.App:
    """Two routers (slug a / b), each pinning canonical name ``dup``."""

    class A(a2kit.Router):
        slug = "a"

        @a2kit.read(canonical_name_override="dup")
        async def one(self) -> dict:
            return {}

    class B(a2kit.Router):
        slug = "b"

        @a2kit.read(canonical_name_override="dup")
        async def two(self) -> dict:
            return {}

    return app_of("collide", A(), B())


# --------------------------------------------------------------------------- #
# §1.1 — Global-uniqueness collision (the headline RED).
# --------------------------------------------------------------------------- #


def test_global_canonical_name_collision_fails_loud() -> None:
    from a2kit.runtime import validate_composition

    app = _colliding_app()
    with pytest.raises(ValueError) as ei:
        validate_composition(app)
    msg = str(ei.value)
    assert "dup" in msg
    # Both offending verbs are named (slug + leaf each).
    assert "a" in msg
    assert "b" in msg
    assert "one" in msg
    assert "two" in msg


# --------------------------------------------------------------------------- #
# §1.2 — Per-surface placement does NOT rescue a collision.
# --------------------------------------------------------------------------- #


def test_disjoint_surfaces_still_collide() -> None:
    from a2kit.runtime import validate_composition

    class A(a2kit.Router):
        slug = "a"

        @a2kit.read(canonical_name_override="foo", surfaces=("cli",))
        async def one(self) -> dict:
            return {}

    class B(a2kit.Router):
        slug = "b"

        @a2kit.read(canonical_name_override="foo", surfaces=("mcp",))
        async def two(self) -> dict:
            return {}

    app = app_of("disjoint", A(), B())
    with pytest.raises(ValueError) as ei:
        validate_composition(app)
    assert "foo" in str(ei.value)


# --------------------------------------------------------------------------- #
# §1.3 — No-build callability.
# --------------------------------------------------------------------------- #


def test_validate_runs_without_full_build() -> None:
    from a2kit.runtime import validate_composition

    class Entity(a2kit.Router):
        slug = "entity"

        @a2kit.read()
        async def update(self, *, id: str = "") -> dict:
            return {"id": id}

    app = app_of("clean", Entity())
    # Never call build(); validate runs and returns None.
    assert validate_composition(app) is None
    # The compose-phase container is left unsealed and mutable.
    assert app.container()._sealed is False  # noqa: SLF001 -- assertion seam

    class _Late:
        pass

    app.provide(_Late, _Late)  # still mutable — no seal happened
    assert app.has_provider(_Late)


# --------------------------------------------------------------------------- #
# §1.4 — Surface-name check available offline.
# --------------------------------------------------------------------------- #


def test_unknown_surface_reported_without_build() -> None:
    from a2kit.runtime import validate_composition

    class Bad(a2kit.Router):
        slug = "bad"

        @a2kit.read(surfaces=("bogus",))
        async def op(self) -> dict:
            return {}

    app = app_of("unknown-surface", Bad())
    with pytest.raises((ValueError, TypeError)) as ei:
        validate_composition(app)
    assert "bogus" in str(ei.value)


# --------------------------------------------------------------------------- #
# §1.5 — Happy path.
# --------------------------------------------------------------------------- #


def test_unique_composition_passes() -> None:
    from a2kit.runtime import validate_composition

    class Entity(a2kit.Router):
        slug = "entity"

        @a2kit.read()
        async def update(self) -> dict:
            return {}

        @a2kit.list_()
        async def search(self) -> list[dict]:
            return []

    class Ontology(a2kit.Router):
        slug = "ontology"

        @a2kit.read()
        async def update(self) -> dict:
            return {}

    app = app_of("unique", Entity(), Ontology())
    # entity_update / entity_search / ontology_update are all distinct.
    assert validate_composition(app) is None


# --------------------------------------------------------------------------- #
# §1.6 — build() invokes the backstop (core-composition MODIFIED).
# --------------------------------------------------------------------------- #


def test_build_invokes_uniqueness_backstop() -> None:
    from a2kit.runtime import build

    app = _colliding_app()
    with pytest.raises(ValueError) as ei:
        build(app)
    msg = str(ei.value)
    assert "dup" in msg
    assert "a" in msg
    assert "b" in msg
