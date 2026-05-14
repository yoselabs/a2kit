"""BDD: ``Resolver`` protocol decouples framework from concrete container.

Covers spec ``di-container-package``: ``Resolver`` is a ``typing.Protocol``
with a minimal surface; the concrete ``Container`` implements it; framework
modules reference the protocol, not the concrete class.
"""

from __future__ import annotations




def test_container_isinstance_resolver() -> None:
    """A default ``Container`` satisfies the ``Resolver`` protocol at runtime."""
    from a2kit.packages.di import Container, Resolver

    container = Container()
    assert isinstance(container, Resolver), (
        "Container does not satisfy Resolver — either Protocol is not "
        "@runtime_checkable or Container is missing required methods"
    )


def test_resolver_minimal_surface() -> None:
    """``Resolver`` protocol surface is exactly: ``get``, ``provide``, ``child``, ``aclose``."""
    from a2kit.packages.di import Resolver

    # Walk all public attributes declared on the Protocol.
    surface = {
        name
        for name in dir(Resolver)
        if not name.startswith("_")
    }

    expected = {"get", "provide", "child", "aclose"}
    extra = surface - expected
    missing = expected - surface

    assert not missing, f"Resolver protocol missing methods: {missing}"
    assert not extra, f"Resolver protocol has unexpected methods: {extra}"


def test_resolver_is_runtime_checkable() -> None:
    """``Resolver`` must be ``@runtime_checkable`` for ``isinstance`` to work."""
    from a2kit.packages.di import Resolver

    # Protocol decorated with @runtime_checkable has _is_runtime_protocol = True.
    assert getattr(Resolver, "_is_runtime_protocol", False), (
        "Resolver must be decorated with @typing.runtime_checkable"
    )
