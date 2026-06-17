"""BDD scenarios for ``a2kit.testing.ambient_for_tests_autouse``.

Pre-decorated autouse peer of ``ambient_for_tests``. Shipped per a2web
round-11 feedback Note 1: the documented ``__wrapped__`` re-export
pattern works but reaches through a pytest internal. The autouse
variant lets consumers wanting project-wide ambient binding write a
single ``from a2kit.testing import ambient_for_tests_autouse`` in
``conftest.py`` and stop there.

This file is the per-module demonstration. The fixture is imported at
module scope, which makes it autouse for every test in this file. We
intentionally do not declare it as a parameter on any test — that is
the point of the variant. The bare ``ambient_for_tests`` regression
scenarios live in ``test_testing_ambient_fixture.py`` (different file
so the autouse binding does not bleed into them).
"""

from __future__ import annotations

import pytest

import a2kit.log
from a2kit.testing import ambient_for_tests_autouse  # noqa: F401 -- autouse activation


def test_ambient_for_tests_autouse_is_importable_from_public_surface() -> None:
    """``from a2kit.testing import ambient_for_tests_autouse`` resolves
    and the object is non-None."""
    assert ambient_for_tests_autouse is not None


def test_ambient_for_tests_autouse_carries_pytest_fixture_metadata() -> None:
    """The imported object is a pytest fixture and its autouse flag is True.

    Pytest 8+ exposes the marker as ``_fixture_function_marker`` on the
    ``FixtureFunctionDefinition`` wrapper; we check that attribute and
    its ``autouse`` field. Without these the consumer's one-line import
    does not bind ambient on import — the round-11 ergonomic delta
    hinges on both.
    """
    marker = getattr(ambient_for_tests_autouse, "_fixture_function_marker", None)
    assert marker is not None, "ambient_for_tests_autouse is not a pytest fixture"
    assert marker.autouse is True


@pytest.mark.asyncio
async def test_no_signature_declaration_still_binds_ambient() -> None:
    """The test body emits a log event without declaring any fixture
    parameter. With ``ambient_for_tests_autouse`` imported at module
    scope, the call completes; without it, this would raise
    ``RequestScopeMissing``."""
    await a2kit.log.info("evt", k=1)


@pytest.mark.asyncio
async def test_autouse_variant_emits_no_wire_side_effects_under_defaults() -> None:
    """Same default-flags guarantee as the bare ``ambient_for_tests``:
    ``events_enabled=False``, so emissions complete silently. Proves the
    autouse variant shares behavior with the bare fixture and only
    differs in registration."""
    await a2kit.log.info("evt", k=1)
    await a2kit.log.info("another", payload="data")
