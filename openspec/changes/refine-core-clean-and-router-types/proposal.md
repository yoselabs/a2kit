# Refine A2K-CORE-CLEAN and tighten Router type fidelity

## Why

Two pieces of post-v0.32-recovery scar tissue are worth cleaning before
the v0.34 release cut, and they fit one change because both touch the
"core source vs. typed extras" boundary.

**Symptom 1 — 24 `A2K-CORE-CLEAN` noqas in `src/`.** The rule says
core source MUST NOT reference feature identifiers like `report_type`,
`list_view`, `report_schema`, `router_slug`, `visibility`,
`timeout_seconds`. But the verb decorators in `src/a2kit/tool.py` and
the Router base in `src/a2kit/routers.py` **legitimately stamp these
into the typed `A2KitMetaExtras` namespace** — that's the whole point
of `A2KitMetaExtras` existing as the typed bag. The rule was authored
before `A2KitMetaExtras` was the canonical surface; it now catches the
wrong shape.

```
Current rule:  "core MUST NOT reference 'report_type' etc. as strings"
Reality:       "core SHALL stamp these via A2KitMetaExtras typed slots"
              → Rule mismatches architecture; suppressions are honest
                 scar tissue rather than fixable code smell.
```

The architectural concern the rule modeled (don't let feature
identifiers leak into core as untyped string keys) is **already
enforced structurally** — you cannot add a new `extras` key without
editing the typed `A2KitMetaExtras` pydantic model. The lint rule is
redundant with the type system.

**Symptom 2 — two `ty: ignore` directives mask Router type tensions.**

- `src/a2kit/routers.py:73` `self.slug = slug` shadows
  `slug: ClassVar[str]`. The ClassVar intent ("subclasses MUST set
  at class scope") fights the instance shadow ("fast lookup via
  `self.slug`"). Both intents are valid but the type annotation can
  only model one.

- `src/a2kit/app.py:553` `router.lifespan()` — the `Router` base
  class doesn't declare a `lifespan` method (it's an optional
  duck-typed convention). The call carries a `type: ignore` plus
  `ty: ignore`.

## What Changes

- **REMOVE** the `A2K-CORE-CLEAN` lint rule and its supporting code
  in `src/a2kit/packages/lint/rules/purity.py`. Delete the rule
  registration in `static.py`. Drop the 24 `# noqa: A2K-CORE-CLEAN`
  suppressions across `metadata.py`, `tool.py`, `schema.py`,
  `routers.py`.

- **MODIFY** the `core-purity` capability spec: drop the "A2K-CORE-CLEAN
  flags untyped feature-identifier references in core" requirement.
  Keep the related `A2K-EXTRA-NAMESPACE` rule (which enforces *typed*
  extras-slot discipline — that one still has architectural weight).

- **MODIFY** `Router.slug` from `ClassVar[str]` to `str`. Remove the
  `self.slug = slug` instance shadow in `Router.__init__`. Subclass
  `slug = "x"` at class scope continues to work (Python class-attr
  lookup falls through to instance). Drop the `ty: ignore` directive
  at `src/a2kit/routers.py:73`.

- **ADD** a `HasLifespan` Protocol in `src/a2kit/lifespan.py` (or
  inline in `app.py`) declaring
  `def lifespan(self) -> AsyncContextManager[None]`. Type
  `_router_lifespan_factory`'s parameter as `Router | HasLifespan`
  and drop the `ty: ignore` directive at `src/a2kit/app.py:553`.

## Impact

- Lint surface: `make lint` becomes ~24 noqas lighter; one entire
  static rule retires; rule count drops by 1 in `static.py`.
- Type surface: two production `ty: ignore`s disappear. Router base
  becomes one annotation simpler.
- No consumer-visible behaviour changes. `Router` subclasses written
  as `class X(Router): slug = "x"; tools = (...)` continue to work
  unchanged.
- Specs touched: `core-purity` (REMOVED requirement), `router-conventions`
  (MODIFIED — slug typing note).
- Compatible with existing `A2KitMetaExtras` typed-extras structural
  guarantees — those provide the same protection more rigorously.
