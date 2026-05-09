"""Coverage for `a2kit.capabilities` — `Cap` enum + `CapabilityRegistry`."""

from __future__ import annotations

import pytest

from a2kit.capabilities import Cap, CapabilityRegistry, capabilities


def test_cap_values_are_lowercase_strings() -> None:
    assert Cap.READ.value == "read"
    assert Cap.WRITE.value == "write"
    assert Cap.DESTRUCTIVE.value == "destructive"
    assert Cap.EXPENSIVE.value == "expensive"
    assert Cap.PII.value == "pii"
    assert Cap.EXTERNAL.value == "external"


def test_module_singleton_is_capability_registry() -> None:
    assert isinstance(capabilities, CapabilityRegistry)


def test_registry_seeds_built_in_caps() -> None:
    reg = CapabilityRegistry()
    known = reg.known()
    assert {"read", "write", "destructive", "expensive", "pii", "external"}.issubset(known)


def test_registry_is_built_in() -> None:
    reg = CapabilityRegistry()
    assert reg.is_built_in("read") is True
    assert reg.is_built_in("custom") is False


def test_registry_register_returns_name_and_adds_to_known() -> None:
    reg = CapabilityRegistry()
    out = reg.register("my-cap_42")
    assert out == "my-cap_42"
    assert "my-cap_42" in reg.known()


def test_registry_known_is_frozen_snapshot() -> None:
    """`known()` returns a frozenset — mutations don't leak back."""
    reg = CapabilityRegistry()
    snap = reg.known()
    assert isinstance(snap, frozenset)
    reg.register("late")
    # snapshot pre-register doesn't include 'late'.
    assert "late" not in snap
    assert "late" in reg.known()


@pytest.mark.parametrize("bad", ["UPPER", "1leading", "-leading", "with space", "with.dot", ""])
def test_registry_register_rejects_bad_names(bad: str) -> None:
    reg = CapabilityRegistry()
    with pytest.raises(ValueError, match="must match"):
        reg.register(bad)


def test_registry_register_idempotent() -> None:
    reg = CapabilityRegistry()
    reg.register("x")
    reg.register("x")
    assert "x" in reg.known()


def test_a2kit_lazy_attr_capabilities() -> None:
    """`a2kit.Cap` resolves via `__getattr__`."""
    import a2kit

    assert a2kit.Cap is Cap
    # `a2kit.capabilities` is also exposed (module name shadows the singleton —
    # the singleton is reachable via `from a2kit.capabilities import capabilities`).
    from a2kit.capabilities import capabilities as cap_singleton

    assert isinstance(cap_singleton, CapabilityRegistry)


def test_a2kit_lazy_attr_unknown_raises() -> None:
    import a2kit

    with pytest.raises(AttributeError, match="no attribute"):
        a2kit.definitely_not_an_attr  # noqa: B018
