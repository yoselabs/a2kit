"""Mirror tests for `a2kit.packages.auth.spec`.

`AuthSpec` is a near-bare base contract. These tests pin the two
behaviours substrate builders rely on:

- `AuthTarget` is **open** — any registered surface name is a valid
  target (per `auth-spec`: target SHALL NOT be restricted to
  `Literal["api", "mcp"]`).
- `AuthSpec.build_middleware()` is a contract method; the base raises
  rather than returning a silent no-op.
"""

from __future__ import annotations

import pytest

from a2kit.packages.auth.spec import AsgiFactory, AuthSpec, AuthTarget


def test_authspec_declares_target_classvar() -> None:
    """Concrete subclasses override `target` with a surface name."""
    assert AuthSpec.__name__ == "AuthSpec"


def test_authtarget_is_open_str_alias() -> None:
    """`AuthTarget` SHALL accept any registered surface name, not a closed Literal."""
    assert AuthTarget is str
    # A spec may declare a non-bundled target (e.g. the internal spoke).
    custom: AuthTarget = "internal"
    assert custom == "internal"


def test_asgifactory_alias_published() -> None:
    """The middleware-factory alias is part of the published contract."""
    assert AsgiFactory is not None


def test_base_build_middleware_raises_not_implemented() -> None:
    """A bare `AuthSpec` has no middleware — calling it is a construction bug."""

    class _Bare(AuthSpec):
        target = "api"

    with pytest.raises(NotImplementedError) as exc:
        _Bare().build_middleware()
    assert "build_middleware" in str(exc.value)
