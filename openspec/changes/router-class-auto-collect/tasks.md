# Tasks — router-class-auto-collect

BDD-first / TDD red → green. The new collection behavior gets a failing
spec/test BEFORE the implementation; the `tools=` removal is proven by a
test that a tuple-free router still registers its tools.

## 1. Collection without `tools=` (RED → GREEN)

- [ ] 1.1 Write a failing test: define a `Router` subclass with two
      `@a2kit.read`-decorated methods and **no** `tools=` tuple; add it to
      an App; assert both tools register. Confirm it FAILS today (current
      `Router.__init__` raises `TypeError` "must define class attribute
      'tools'").
- [ ] 1.2 Write a failing test: a decorated method on a tuple-free router
      is callable end-to-end (dispatch resolves it, DI injects its typed
      kwargs). Confirm RED.
- [ ] 1.3 Implement `Router.__init_subclass__` decorator-marker
      collection: iterate `vars(cls)` (NOT `dir(cls)`), keep only
      attributes whose `_get_meta(...)` returns verb metadata, store as
      the collected tool set. Make §1.1–1.2 GREEN.
- [ ] 1.4 Remove the `tools: ClassVar[tuple]` attribute, its
      `Router.__init__` validation block (`routers.py:131-168`), and the
      "tuple after method definitions" docstring guidance. Update the
      `Router` class docstring to describe marker collection and to keep
      the explicit "no `dir()` walk" promise.

## 2. NOT a `dir()` walk (guard test)

- [ ] 2.1 Write a test proving collection is marker-driven, not
      structural: a `Router` subclass with a plain (undecorated) helper
      method MUST NOT register it as a tool. This locks in the
      decorator-marker semantics ADR 0028 decision 7 requires and
      prevents a future regression to `dir()`-walk magic.
- [ ] 2.2 Write a test for inheritance MRO: a subclass that inherits a
      decorated method from a base (without re-declaring) still registers
      it; an overridden method registers the override. Confirm GREEN.

## 3. Retire the drift check

- [ ] 3.1 Write a test asserting `add_router` no longer raises
      `A2KitDecoratedMethodNotInTools` for a tuple-free router (the error
      class is now unreachable — there is no tuple to drift from).
- [ ] 3.2 Remove the `A2KitDecoratedMethodNotInTools` drift-detection
      logic from `App.add_router` and (if no longer referenced) the
      exception class. Make §3.1 GREEN; confirm no other caller depends
      on the exception.

## 4. Enricher unification (RED → GREEN)

- [ ] 4.1 Write a failing test: an in-class `@a2kit.enricher`-marked
      method is collected and fires with the existing narrow/wide dispatch
      semantics (narrow on isinstance, wide on `Exception`/`BaseException`)
      and the `AppError | None` return contract. Confirm RED.
- [ ] 4.2 Add the `@a2kit.enricher` marker to the verb-decorator surface
      and collect enricher-marked methods in `__init_subclass__` (same
      hook as §1.3). Make §4.1 GREEN.
- [ ] 4.3 Retire the post-construction `@router.enricher` instance
      decorator as the authoring channel; relax the class-body
      `enrichers`/`enrich` ban (no longer ambiguous with the removed
      tuple). Update tests that used the instance form to the in-class
      marked-method form.
- [ ] 4.4 Confirm chain order is unchanged: per-tool inline → router
      enrichers (declaration order) → app enrichers → defect quarantine;
      first non-None `AppError` wins.

## 5. Spec + ADR doc tasks

- [ ] 5.1 Land `specs/router-conventions/spec.md` (MODIFIED): drop the
      `tools=` requirement text, replace with marker-collection; remove
      the `A2KitDecoratedMethodNotInTools` requirement; rewrite the
      enricher requirement for the in-class `@a2kit.enricher` form.
- [ ] 5.2 **Update ADR 0002 status linkage (doc task).** Edit
      `docs/adr/0002-author-annotation-surface.md`: note in its Status /
      Consequences that decision 7 of ADR 0028 **amends** the
      explicit-`tools=`-tuple stance (the `__init_subclass__`
      decorator-marker collection replaces it), and cross-link ADR 0028.
      ADR 0002 is *amended*, not *superseded* — its pydantic.Field core
      decision stands; only set a "see also / amended by ADR 0028" pointer.
- [ ] 5.3 Update `src/a2kit/routers.py` examples and any author-facing
      docs that show a `tools=` tuple (remove the line); update the
      `CHANGELOG.md` BREAKING entry (delete `tools=`; enricher authoring
      moves in-class).

## 6. Verify (GREEN)

- [ ] 6.1 New tests from §1–§4 pass.
- [ ] 6.2 Existing router-conventions / dispatch / enricher tests stay
      green after migration to the tuple-free + in-class-enricher shape.
- [ ] 6.3 `public-api-tier-snapshot` static derivation still produces the
      same tool set (decorators remain AST-visible without the tuple).
- [ ] 6.4 Full suite green, output pristine; lint / `ty check src/` /
      a2kit-static / ruff gates green on all touched files.

## 7. Close out

- [ ] 7.1 Confirm co-ship readiness with `native-tree-homomorphism`,
      `surfaces-projection-axis`, and `app-as-peer-root` (one Wave 2
      breaking release; one consumer migration table).
- [ ] 7.2 Verify the consumer migration is mechanical: a2atlassian /
      a2db / a2web each only delete `tools=` lines and move any
      `@router.enricher` to in-class `@a2kit.enricher`.
