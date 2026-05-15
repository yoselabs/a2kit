"""BDD scenarios for ``a2kit.testing.ambient_for_tests``.

Pytest fixture that establishes an LDD ambient so tests calling
orchestrator / phase functions directly (bypassing
``TestClient.invoke``) don't trip :class:`AmbientContextMissing`.

Shipped per a2web round-10 feedback Friction A2.

Design choices captured here:
- **Opt-in, not autouse-by-default.** Consumers re-export under
  their own autouse if they want project-wide ambient. Preserves
  the loud-by-default ``AmbientContextMissing`` contract outside
  tests that explicitly request the ambient.
- **Defaults: events=False, reports=False, ctx=null_context().**
  Matches the universal a2web pattern; consumers needing different
  flags wrap ``ldd_state_for_call`` themselves.
"""

from __future__ import annotations

import pytest

import a2kit
from a2kit.exceptions import AmbientContextMissing
from a2kit.testing import ambient_for_tests


def test_ambient_for_tests_is_importable_from_public_surface() -> None:
    """The fixture is reachable as ``from a2kit.testing import ambient_for_tests``.

    The strongest proof that pytest treats it as a fixture is the other
    test in this file that uses it as a parameter — if pytest didn't
    recognise it, collection would fail. Here we just confirm the import
    path resolves and the object is non-None.
    """
    assert ambient_for_tests is not None


@pytest.mark.asyncio
async def test_using_fixture_allows_ldd_event_to_complete(
    ambient_for_tests: None,  # noqa: ARG001 -- fixture activation
) -> None:
    """Inside a test that requests the fixture, ``a2kit.ldd.event(...)``
    completes without raising ``AmbientContextMissing``."""
    await a2kit.ldd.event("evt", k=1)


@pytest.mark.asyncio
async def test_without_fixture_ldd_event_raises_mode_b() -> None:
    """Without the fixture (and without any other ambient setup), the
    same call raises ``AmbientContextMissing`` Mode A — proves the
    fixture is opt-in, not autouse."""
    with pytest.raises(AmbientContextMissing):
        await a2kit.ldd.event("evt", k=1)


@pytest.mark.asyncio
async def test_event_emission_completes_under_default_flags(
    ambient_for_tests: None,  # noqa: ARG001
) -> None:
    """With default flags (events_enabled=False), event emissions
    complete without raising. The null-context wire emit is a silent
    no-op, so we observe completion-without-error as the proof.

    (Reports under default reports_enabled=False are NOT smoke-tested
    here — ``a2kit.ldd.report(...)`` checks ``state.report_type`` before
    the enabled flag, so report calls without a declared type raise
    ``ReportTypeNotDeclared`` independent of the kill switch. That's
    the framework's normal invariant; the fixture doesn't change it.)
    """
    await a2kit.ldd.event("evt", k=1)
    await a2kit.ldd.event("another", payload="data")
