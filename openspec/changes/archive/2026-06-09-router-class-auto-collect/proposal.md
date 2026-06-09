## Why

Today a `Router` subclass must list every tool **twice**: once where the
method is defined (decorated `@a2kit.read/write/list_/tool`), and again at
the end of the class body in a `tools: ClassVar[tuple[Callable, ...]]`
tuple (`routers.py:89`, enforced in `Router.__init__` at `:131-168` and
re-validated by `add_router` via the `A2KitDecoratedMethodNotInTools`
drift check). The tuple is pure duplication of information the decorator
already carries, and it is a recurring footgun:

- It MUST be placed **after** the method definitions so the names are
  bound when the tuple is evaluated — an ordering rule with no analogue
  anywhere else in the surface and easy to get wrong.
- Adding a tool means editing two places; forgetting the tuple line is a
  silent omission caught only at `add_router` time (or, worse, a tool
  that simply never registers if the drift check is bypassed).
- The whole machinery — `tools=`, the per-entry `callable`/`__name__`
  validation, and the separate `A2KitDecoratedMethodNotInTools`
  drift-detection requirement — exists *only* to keep the tuple in sync
  with the decorators. The decorator marker is already the source of
  truth; the tuple is a manually-maintained shadow copy.

a2kay (the downstream consumer) flagged the end-of-class-body tuple as the
single most error-prone part of router authoring. ADR 0028 decision 7
resolves it: the `@a2kit`-marker on the method **is** the registration.

## What Changes

`Router.__init_subclass__` auto-collects every method carrying an
`@a2kit.read/write/list_/tool` marker into the router's tool set at
class-definition time. The manual `tools=` tuple is **removed** entirely.
Enrichers unify onto the same marked-method pattern (`@a2kit.enricher`),
folding away the former instance-decorator special case
(`router = R(); @router.enricher`).

Critically, this is **decorator-marker collection**, NOT a `dir()` /
introspection walk: the metaclass hook reads a marker attribute that the
decorator stamped onto the method (the same `_get_meta` metadata used
today). It does not enumerate attributes by name, by naming convention,
or by `dir(self)`. The marker is the most local, most AI-legible
declaration possible — it sits *on* the method.

- **`tools=` tuple removed.** Authors delete their `tools = (a, b, c)`
  line; nothing replaces it. A decorated method is registered by virtue
  of being decorated.
- **`__init_subclass__` collects marked methods.** Walks `cls.__dict__`
  (own attributes, MRO-aware for inheritance), keeping only those whose
  `_get_meta(...)` returns verb-decorator metadata.
- **Drift check retired.** With no tuple to drift from, the
  `A2KitDecoratedMethodNotInTools` requirement becomes vacuous and is
  removed — the registration error class is impossible by construction.
- **Enrichers unify.** `@a2kit.enricher`-marked methods are collected by
  the same hook; the class-body `enrichers`/`enrich` ban and the
  post-construction `@router.enricher` instance decorator are replaced by
  the in-class marked-method form.

## Capabilities

### Modified Capabilities

- `router-conventions` — drop the `tools=` tuple and its per-entry
  validation; `Router.__init_subclass__` auto-collects `@a2kit`-marked
  methods (decorator-marker collection, not `dir()`); retire the
  `A2KitDecoratedMethodNotInTools` drift check; enrichers unify onto the
  same in-class `@a2kit.enricher` marked-method pattern (replacing the
  `@router.enricher` instance decorator).

## Impact

- **BREAKING** for every existing router that declares `tools=`. The
  migration is **mechanical removal**: delete the `tools = (...)` line.
  No rename, no rewrite — the decorated methods stay exactly as written.
  Enricher authors move from `router = R(); @router.enricher def f(...)`
  to an in-class `@a2kit.enricher def f(self, ...)`.
- **Amends ADR 0002.** ADR 0002 ("Pydantic.Field as the per-parameter
  author annotation surface") explicitly rejected `__init_subclass__`
  registries and `dir()`-walk magic. ADR 0028 decision 7 reverses that
  stance **for the narrow case of decorator-marker collection only**:
  the original objection was to *magic* (naming-convention / `dir()`
  collection), and decorator-marker collection is the *least*-magical
  option (the marker is on the method). ADR 0002's broader anti-`dir()`
  position is preserved; only the explicit-tuple requirement is amended.
- Affected consumers: a2atlassian / a2db / a2web (each deletes `tools=`
  lines). Affected internals: `src/a2kit/routers.py` (`Router`),
  `App.add_router` (drift check removal), the verb-decorator surface
  (`@a2kit.enricher`), and the public-API tier snapshot (decorators stay
  AST-visible, so the static derivation still works).
- **Co-ships** as the authoring half of the Wave 2 breaking surface,
  together with `native-tree-homomorphism`, `surfaces-projection-axis`,
  and `app-as-peer-root` (the rename + the new axis + the authoring shape
  are one breaking surface). See `docs/SURFACE_ARCHITECTURE.md` §7.

## Non-goals

- **NO `dir()` / introspection walk.** Collection is strictly
  decorator-marker driven; the framework never enumerates `dir(self)`, a
  naming convention, or untagged methods. ADR 0002's rejection of
  `dir()`-walk magic stands — this change does not reintroduce it.
- **Not** the FastAPI instance + `@router.read` form. Routers stay
  classes with class-attribute config; the instance-decorator pattern is
  explicitly not adopted (ADR 0028 decision 7 rationale).
- **Not** the App-level authoring shape. `App` becoming a peer class with
  the same marked-method collection is `app-as-peer-root` (co-ships, but
  a separate change). This change covers `Router` only.
- **Not** the canonical-name rename or the `surfaces` matrix — those are
  `native-tree-homomorphism` and `surfaces-projection-axis` respectively.
