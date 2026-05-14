"""BDD contract for consolidate-lifecycle-on-async-cm-protocol task 1.2.

``app.singleton(...)`` accepts three call shapes:

- ``singleton(SomeClass)`` — class is the factory; registered type is the class
- ``singleton(factory)`` — return-type annotation provides the type
- ``singleton(BaseClass, factory)`` — explicit base-type override

Unannotated callables raise ``TypeError`` at registration.
"""

from __future__ import annotations

import pytest

import a2kit

pytestmark = pytest.mark.skip(reason="contract for consolidate-lifecycle-on-async-cm-protocol; un-skip when impl lands")


class _Thing:
    pass


class _Sub(_Thing):
    pass


def test_class_as_factory_registers_class() -> None:
    app = a2kit.App("x")
    app.singleton(_Thing)
    assert _Thing in app.singletons()


def test_factory_with_return_annotation_registers_return_type() -> None:
    def make() -> _Thing:
        return _Thing()

    app = a2kit.App("x")
    app.singleton(make)
    assert _Thing in app.singletons()


def test_async_factory_with_return_annotation_registers_return_type() -> None:
    async def make() -> _Thing:
        return _Thing()

    app = a2kit.App("x")
    app.singleton(make)
    assert _Thing in app.singletons()


def test_explicit_base_type_override() -> None:
    def make() -> _Sub:
        return _Sub()

    app = a2kit.App("x")
    app.singleton(_Thing, make)
    assert _Thing in app.singletons()
    assert _Sub not in app.singletons()


def test_unannotated_lambda_raises_typeerror_with_hint() -> None:
    app = a2kit.App("x")
    with pytest.raises(TypeError) as ei:
        app.singleton(lambda: _Thing())
    msg = str(ei.value)
    assert "return annotation" in msg
    assert "app.singleton(T, factory)" in msg
