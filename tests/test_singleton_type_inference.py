"""BDD contract for consolidate-lifecycle-on-async-cm-protocol task 1.2.

``app.provide(...)`` accepts three call shapes:

- ``singleton(SomeClass)`` — class is the factory; registered type is the class
- ``singleton(factory)`` — return-type annotation provides the type
- ``singleton(BaseClass, factory)`` — explicit base-type override

Unannotated callables raise ``TypeError`` at registration.
"""

from __future__ import annotations


import a2kit


class _Thing:
    pass


class _Sub(_Thing):
    pass


def test_class_as_factory_registers_class() -> None:
    app = a2kit.App("x")
    app.provide(_Thing)
    assert _Thing in app.providers()


def test_factory_with_return_annotation_registers_return_type() -> None:
    def make() -> _Thing:
        return _Thing()

    app = a2kit.App("x")
    app.provide(make)
    assert _Thing in app.providers()


def test_async_factory_with_return_annotation_registers_return_type() -> None:
    async def make() -> _Thing:
        return _Thing()

    app = a2kit.App("x")
    app.provide(make)
    assert _Thing in app.providers()


def test_explicit_base_type_override() -> None:
    def make() -> _Sub:
        return _Sub()

    app = a2kit.App("x")
    app.provide(_Thing, make)
    assert _Thing in app.providers()
    assert _Sub not in app.providers()


