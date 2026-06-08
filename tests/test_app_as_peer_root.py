"""App-as-peer-root: ``App`` authored as a subclassable class (ADR 0028 Wave 2).

Covers the transition-tolerant core: an ``App`` subclass collects app-level
``@a2kit`` verbs (rendered BARE — no slug prefix), composes router *classes*
via the ``routers`` ClassVar (reference-composition, replacing
``add_router``), installs the ``providers`` ClassVar, collects class-body
``@a2kit.enricher`` methods, and reads per-surface config from a ``config``
class attr. The imperative ``App("svc").add_router(...)`` form stays working
during the transition.

Gherkin (mirrors `openspec/changes/app-as-peer-root`):

  Scenario: app-level verb is collected and bare-named
    GIVEN class Kay(App) with @a2kit.read def health
    WHEN Kay() is constructed
    THEN app.tools() has one descriptor named "health" (no slug prefix)

  Scenario: routers ClassVar composes router classes
    GIVEN class Kay(App): routers = (Entity,)
    WHEN Kay() is constructed
    THEN Entity's tools appear in app.tools() with slug-qualified names

  Scenario: providers ClassVar installs
    GIVEN class Kay(App): providers = (Store,)
    THEN app has a provider for Store

  Scenario: class-body enricher is collected
    GIVEN class Kay(App) with @a2kit.enricher def on_x
    THEN the app enricher chain contains it
"""

from __future__ import annotations

import a2kit
from a2effect import AppError
from pydantic import BaseModel


class _Boom(AppError):
    kind = "input"


class _Health(BaseModel):
    ok: bool


class _Item(BaseModel):
    id: int


class _Entity(a2kit.Router):
    slug = "entity"

    @a2kit.read()
    async def update(self) -> _Item:
        return _Item(id=1)


def test_app_level_verb_collected_and_bare_named() -> None:
    """An ``@a2kit`` method on an App subclass projects as a bare top-level tool."""

    class Kay(a2kit.App):
        name = "kay"

        @a2kit.read()
        async def health(self) -> _Health:
            return _Health(ok=True)

    app = Kay()
    names = {d.name for d in app.tools()}
    assert "health" in names  # bare leaf — NOT "kay_health"
    assert "kay_health" not in names


def test_routers_classvar_composes_router_classes() -> None:
    """``routers = (Entity,)`` composes the router with NO add_router call."""

    class Kay(a2kit.App):
        name = "kay"
        routers = (_Entity,)

    app = Kay()
    names = {d.name for d in app.tools()}
    assert "entity_update" in names  # slug-qualified under the router


def test_providers_classvar_installs() -> None:
    class _Store:
        pass

    class Kay(a2kit.App):
        name = "kay"
        providers = (_Store,)

    app = Kay()
    assert app.has_provider(_Store)


def test_class_body_enricher_collected() -> None:
    class Kay(a2kit.App):
        name = "kay"

        @a2kit.enricher
        def on_value_error(self, exc: ValueError) -> _Boom | None:
            return _Boom()

    app = Kay()
    # The app enricher chain holds one (filter_type, fn) entry.
    assert any(ft is ValueError for ft, _ in app._enrichers)


def test_name_from_class_attr_or_positional() -> None:
    class Kay(a2kit.App):
        name = "kay"

    assert Kay().name == "kay"
