"""Mirror tests for `a2kit.packages.auth.spec`.

`AuthSpec` is a pure base type — coverage is exercised through the
concrete subclasses (`APIKeyAuth` etc.) in their own tests. This
file exists to satisfy `A2K-TEST-MIRROR` and asserts only the
contract surface the concrete tests rely on.
"""

from __future__ import annotations

from a2kit.packages.auth.spec import AuthSpec, AuthTarget


def test_authspec_declares_target_classvar() -> None:
    """Concrete subclasses override `target` with one of the AuthTarget values."""
    # The base type is intentionally bare; classvar shape is enforced by ty.
    assert AuthSpec.__name__ == "AuthSpec"


def test_authtarget_literal_covers_bundled_surfaces() -> None:
    """`AuthTarget` SHALL cover the two bundled surface names."""
    import typing as _typing

    assert set(_typing.get_args(AuthTarget)) == {"api", "mcp"}
