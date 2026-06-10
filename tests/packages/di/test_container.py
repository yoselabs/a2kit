"""BDD baseline for the Container resolution surface.

The legacy DI methods (``register`` / ``register_singleton`` / ``resolve`` /
``aresolve`` / ``has`` / ``has_async_singleton`` / ``has_any_async_singletons``)
were removed. The old names are gone — accessing one raises the
language-default ``AttributeError``, nothing more. Surface inventory pins the
public attribute set.
"""

from __future__ import annotations

import pytest

from a2kit.packages.di.container import Container


class _T:
    pass


@pytest.mark.parametrize(
    "name",
    [
        "register",
        "register_singleton",
        "resolve",
        "aresolve",
        "has",
        "has_async_singleton",
        "has_any_async_singletons",
    ],
)
def test_removed_legacy_method_raises_attribute_error(name: str) -> None:
    c = Container()
    with pytest.raises(AttributeError):
        getattr(c, name)


def test_new_surface_present() -> None:
    """The v0.36+ resolution surface is present on Container."""
    for name in (
        "provide",
        "has_provider",
        "providers_view",
        "get",
        "resolve_params",
        "call_scope",
        "child",
        "aclose",
    ):
        assert hasattr(Container, name), f"missing surface member: {name}"
