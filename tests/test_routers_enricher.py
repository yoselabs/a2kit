"""Router subclasses accept ``enricher`` three ways: kwarg, attribute, constructor."""

from __future__ import annotations

from a2kit.metadata import get_meta
from a2kit.routers import Router


def _enricher_a(exc: Exception, _tool: str | None = None) -> Exception:
    return exc


def _enricher_b(exc: Exception, _tool: str | None = None) -> Exception:
    return exc


def test_class_kwarg_form_captures_enricher():
    class TasksRouter(Router, enricher=_enricher_a):
        pass

    assert TasksRouter.enricher is _enricher_a or callable(TasksRouter.enricher)
    # Bound at class scope as staticmethod (no descriptor binding to instance).
    assert TasksRouter().enricher is _enricher_a


def test_class_kwarg_applied_to_decorated_tools():
    import a2kit

    class TasksRouter(a2kit.Router, enricher=_enricher_a):
        @a2kit.read("get")
        async def get(self) -> dict:
            return {}

    fn = TasksRouter().tools()[0]
    meta = get_meta(fn)
    assert meta is not None
    assert meta.enricher is _enricher_a


def test_bare_function_attribute_auto_wraps():
    class TasksRouter(Router):
        enricher = _enricher_a  # bare function, no staticmethod()

    # Without auto-wrap, accessing via instance would bind `self`.
    assert TasksRouter().enricher is _enricher_a


def test_legacy_staticmethod_attribute_still_works():
    class TasksRouter(Router):
        enricher = staticmethod(_enricher_a)

    assert TasksRouter().enricher is _enricher_a


def test_init_arg_overrides_class_kwarg():
    class TasksRouter(Router, enricher=_enricher_a):
        pass

    r = TasksRouter(enricher=_enricher_b)
    # The constructor arg becomes the effective enricher applied to tools.
    # We can't observe `r.enricher` directly because __init__ doesn't store it on instance,
    # but we can check via the tools — except this Router has no tools.
    # Instead, exercise via decorated tool:
    import a2kit

    class TasksRouterT(a2kit.Router, enricher=_enricher_a):
        @a2kit.read("get")
        async def get(self) -> dict:
            return {}

    fn = TasksRouterT(enricher=_enricher_b).tools()[0]
    meta = get_meta(fn)
    assert meta is not None
    assert meta.enricher is _enricher_b


def test_class_kwarg_overrides_class_attribute():
    """When BOTH `enricher = staticmethod(A)` and class kwarg `enricher=B` declared,
    the kwarg wins."""

    class TasksRouter(Router, enricher=_enricher_b):
        enricher = staticmethod(_enricher_a)  # noqa: F811  (intentional shadow)

    # The class kwarg sets cls.enricher AFTER the body executes.
    # Actually Python order: class body executes first (sets attr), then
    # __init_subclass__ runs with the kwarg. Our impl returns early if the
    # kwarg is non-None, so the kwarg wins.
    assert TasksRouter().enricher is _enricher_b
