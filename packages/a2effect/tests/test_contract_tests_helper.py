"""BDD scenarios for error-contract-tests / contract_tests helper."""

from dataclasses import dataclass, field
from typing import Any

from a2effect import AppError
from a2effect.testing import contract_tests


class _NotFound(AppError):
    kind = "input"


class _InvalidId(AppError):
    kind = "input"


class _Infra(AppError):
    kind = "infra"
    retryable = True


@dataclass
class _Tool:
    name: str
    raises: tuple[type[AppError], ...]


@dataclass
class _App:
    tools: list[_Tool]
    enrichers: list = field(default_factory=list)


def test_contract_tests_generates_envelope_round_trip() -> None:
    app = _App(tools=[_Tool("fetch", (_NotFound, _InvalidId))])
    tests = contract_tests(app, dead_enricher=False, surface_parity=False)
    assert "test_envelope_round_trip" in tests


def test_contract_tests_envelope_round_trip_passes_for_valid_setup() -> None:
    app = _App(tools=[_Tool("fetch", (_NotFound,))])
    tests = contract_tests(app, dead_enricher=False, surface_parity=False)
    # Calling the parametrized test with the case args should pass.
    tests["test_envelope_round_trip"]("fetch", _NotFound)  # type: ignore[attr-defined]


def test_contract_tests_disables_dead_enricher_category() -> None:
    app = _App(tools=[_Tool("fetch", (_NotFound,))])
    tests = contract_tests(app, dead_enricher=False, surface_parity=False)
    assert "test_dead_enricher" not in tests


def test_contract_tests_dead_enricher_detects_orphan() -> None:
    def orphan_enricher(exc: Exception) -> _Infra | None:
        return None

    app = _App(
        tools=[_Tool("fetch", (_NotFound,))],
        enrichers=[orphan_enricher],
    )
    tests = contract_tests(app, envelope_round_trip=False, surface_parity=False)
    assert "test_dead_enricher" in tests
    import pytest

    with pytest.raises(BaseException):  # noqa: PT011
        tests["test_dead_enricher"]("orphan_enricher", "_Infra")  # type: ignore[attr-defined]


def test_contract_tests_dead_enricher_passes_when_all_covered() -> None:
    def covered_enricher(exc: Exception) -> _NotFound | None:
        return None

    app = _App(
        tools=[_Tool("fetch", (_NotFound,))],
        enrichers=[covered_enricher],
    )
    tests = contract_tests(app, envelope_round_trip=False, surface_parity=False)
    # No-op test should be present and callable without raising
    tests["test_dead_enricher"]()


def test_contract_tests_surface_parity_skipped_when_renderer_absent() -> None:
    app = _App(tools=[_Tool("fetch", (_NotFound,))])
    tests = contract_tests(app, envelope_round_trip=False, dead_enricher=False)
    assert "test_surface_parity" not in tests


def test_contract_tests_surface_parity_detects_drift() -> None:
    class _AppWithRenderer:
        tools = [_Tool("fetch", (_NotFound,))]
        enrichers: list[Any] = []

        @staticmethod
        def render_envelope_for(surface: str, exc: AppError) -> dict[str, Any]:  # noqa: ARG004
            env = exc.to_envelope_dict()
            if surface == "http":
                env["hint"] = "WRONG"  # introduce surface drift
            return env

    tests = contract_tests(_AppWithRenderer(), envelope_round_trip=False, dead_enricher=False)
    import pytest

    with pytest.raises(BaseException):  # noqa: PT011
        tests["test_surface_parity"]("fetch", _NotFound)  # type: ignore[attr-defined]


def test_contract_tests_surface_parity_passes_when_aligned() -> None:
    class _AppWithRenderer:
        tools = [_Tool("fetch", (_NotFound,))]
        enrichers: list[Any] = []

        @staticmethod
        def render_envelope_for(surface: str, exc: AppError) -> dict[str, Any]:  # noqa: ARG004
            return exc.to_envelope_dict()

    tests = contract_tests(_AppWithRenderer(), envelope_round_trip=False, dead_enricher=False)
    tests["test_surface_parity"]("fetch", _NotFound)  # type: ignore[attr-defined]
