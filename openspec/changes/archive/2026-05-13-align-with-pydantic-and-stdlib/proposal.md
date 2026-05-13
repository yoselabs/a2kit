# Align with pydantic and stdlib

## Why

A codebase audit asked: "where did we re-invent something pydantic or
stdlib already provides?" Three concrete shims came back.

**R1 — `a2kit.Param` is a one-line wrapper around `pydantic.Field`.**
`src/a2kit/params.py` defines `Param(description, **extras)` which
just calls `pydantic.Field(description=description, **extras)` and
returns a `FieldInfo`. The reverse helper `description_of(annotation)`
reads `getattr(meta, "description", None)` from
`typing.get_args(annotation)` — pure pydantic FieldInfo introspection.
The shim adds zero capability beyond pydantic. Tool authors should
write `Annotated[T, pydantic.Field(description="...")]` directly;
that is already the canonical pattern for Pydantic body-model fields
and a2kit's MCP / CLI builders already read it correctly via
`description_of`.

**R4 — `A2KitMeta.extra: dict[str, Any]` is string-keyed soup.**
`src/a2kit/metadata.py` types per-tool metadata's open extension
slot as `dict[str, Any]`. Known keys today: `a2kit.report_type`,
`a2kit.report_schema`, `a2kit.router_slug`, `a2kit.surfaces`,
`a2kit.list_view`. Every consumer reads them as
`meta.extra.get("a2kit.report_type")` with no type guarantees.
A `BaseModel` with named fields gives us type checking, IDE
completion, and a single source of truth for what extras exist.

**R12 — `_param_cache: dict[int, list[_ParamSpec]]` keyed by
`id(factory)` is a latent bug.** `src/a2kit/packages/di/container.py:133`
keys the parameter-introspection cache by integer factory id. The
design note in `src/a2kit/signature.py` records that this pattern
was already tried for tool-signature caching and abandoned because
**Python recycles function ids across nested test scopes, producing
stale cache hits**. The container has the same latent bug; the fix
is `weakref.WeakKeyDictionary` keyed on the factory object itself.

All three changes are small, mechanical, and independent of the
sibling proposals (`explicit-router-surface`, `loud-degrade-everywhere`).
This change lands them together because they share a single
narrative ("trust the platform we already depend on") and the
spec deltas are tightly scoped to three capabilities.

## What Changes

### R1 — Drop `a2kit.Param`, use `pydantic.Field` directly

- Remove `Param` function from `src/a2kit/params.py`.
- Remove `"Param"` from `src/a2kit/__init__.py`'s `_LAZY_ATTRS`.
- Move `description_of(annotation)` to a new private module
  `src/a2kit/_field_introspect.py`. `params.py` is deleted (it
  would otherwise become a one-symbol module whose name no longer
  matches its content). See design D-PARAM-DROP for rationale.
- Update every doctring/example/README that references `a2kit.Param`
  to `pydantic.Field(description="...")`.
- No deprecation cycle: the project is pre-1.0, `Param` was
  introduced two minor versions ago, and the migration is a
  one-line `sed`.

### R4 — Replace `A2KitMeta.extra: dict[str, Any]` with typed model

- Add `class A2KitMetaExtras(BaseModel)` in `src/a2kit/metadata.py`
  with named fields:
  - `report_type: type | None = None`
  - `report_schema: dict[str, Any] | None = None`
  - `router_slug: str | None = None`
  - `surfaces: Surface | None = None` (carried as the existing
    `Surface` flag-enum)
  - `list_view: ListViewSettings | None = None`
  - `model_config = ConfigDict(arbitrary_types_allowed=True)` —
    `type` and `Surface` aren't pydantic-native scalars.
- Change `A2KitMeta.extra: dict[str, Any]` → `A2KitMeta.extras: A2KitMetaExtras`.
- Update every reader (`meta.extra.get("a2kit.report_type")`
  → `meta.extras.report_type`):
  - `src/a2kit/packages/mcp/server.py` (2 sites)
  - `src/a2kit/packages/cli/builder.py` (2 sites)
  - `src/a2kit/packages/cli/schemas.py` (2 sites)
  - `src/a2kit/packages/testing/client.py` (1 site)
- Update writers:
  - `src/a2kit/routers.py` (router slug stamp)
  - `src/a2kit/surface.py` / `src/a2kit/tool.py` (surface stamp)
  - `src/a2kit/packages/mcp/reports.py` (report type + schema stamp)
  - `src/a2kit/tool.py` (list_view stamp)
- Verb decorators and routers write to the typed model directly via
  attribute access. `stage_extra` is reshaped to set the named
  attribute (a one-liner) rather than translate string keys.
- Drop the `EXTRA_TYPE_KEY` / `EXTRA_SCHEMA_KEY` / `_ROUTER_SLUG_KEY` /
  `SURFACE_META_KEY` string constants. They become attribute names.
- The lint rule `rule_purity` (which guards against feature-name
  leaks via known extras keys) loses its string-key list and
  inspects typed attribute access instead.

### R12 — `_param_cache` keyed by `id(factory)` → `WeakKeyDictionary`

- In `src/a2kit/packages/di/container.py`, replace:
  ```python
  self._param_cache: dict[int, list[_ParamSpec]] = {}
  ```
  with
  ```python
  self._param_cache: weakref.WeakKeyDictionary[Factory, list[_ParamSpec]] = weakref.WeakKeyDictionary()
  ```
- Update the cache read/write sites (currently keyed by
  `id(factory)`) to use the factory object itself.
- Add a regression test that exercises the failure mode the
  comment in `signature.py` warns about: register a factory in a
  nested scope, let it be garbage-collected, register a *different*
  factory whose object id happens to match (best-effort: rely on
  CPython id-recycling under refcounting), assert the cache does
  not hand back a stale `_ParamSpec` list.

## Capabilities

### Modified Capabilities

- `tool-description-contract` — the "Per-parameter descriptions via
  `a2kit.Param`" requirement is reworded to point at `pydantic.Field`
  as the canonical surface. The positional-shorthand and
  `TypeError`-on-double-description scenarios are removed (pydantic
  `Field` has no such shorthand and no such collision). The
  Pydantic-Field-for-body-models requirement extends to cover direct
  kwargs by clause; the two requirements collapse into one.
- `tool-descriptors` — `ToolDescriptor`'s relationship to
  `A2KitMeta.extras` is documented (descriptors read typed extras
  for `report_type` and `format_hint` derivation).
- `di-container-package` — the container's parameter cache is
  required to use `weakref.WeakKeyDictionary` keyed on the factory
  object, NOT `id(factory)`. The id-keyed pattern is forbidden by
  scenario.

## Impact

- **Affected code**:
  - `src/a2kit/params.py` — **deleted**. The module's only
    remaining symbol (`description_of`) moves to
    `src/a2kit/_field_introspect.py` (new private module).
  - `src/a2kit/__init__.py` — `Param` lazy-attr entry removed.
  - `src/a2kit/metadata.py` — `A2KitMetaExtras` added; `extra` → `extras`.
  - `src/a2kit/surface.py`, `src/a2kit/routers.py`, `src/a2kit/tool.py`,
    `src/a2kit/packages/mcp/reports.py` — write through typed fields.
  - `src/a2kit/packages/mcp/server.py`, `src/a2kit/packages/cli/builder.py`,
    `src/a2kit/packages/cli/schemas.py`, `src/a2kit/packages/testing/client.py`
    — read typed fields.
  - `src/a2kit/packages/di/container.py` — `_param_cache` →
    `WeakKeyDictionary`.
  - `examples/`, `README.md` — `a2kit.Param` → `pydantic.Field` in
    code samples.

- **APIs**: BREAKING for any tool that uses `a2kit.Param`.
  Migration: `s/a2kit\.Param\((.*)\)/pydantic.Field(description=\1)/`
  for positional callers, identity rewrite for keyword callers.
  No known external consumers.

  BREAKING for any extension that reaches into `meta.extra` by
  string key. Migration is to attribute access; the attribute
  names match the trailing segment of the old keys (no leading
  `a2kit.` namespace).

- **Dependencies**: none added; `pydantic` is already a hard
  dependency and `weakref` is stdlib.

- **CI cost**: negligible. `A2KitMetaExtras` construction at
  decoration time adds <1µs per tool; decoration is one-shot.

- **Risk**:
  - The typed-extras refactor touches eight call sites across
    five files. Mitigation: do it in one sweep so the dict-access
    and attribute-access forms never coexist on `main`.
  - The lint-rule purity check (`rule_purity`) currently lists
    extras keys as strings. After this change those strings no
    longer exist in source; the rule shifts to attribute names.
    The sibling `loud-degrade-everywhere` proposal already
    intends to rework purity rules; this change makes a minimal
    adjustment and leaves the larger rework to that proposal.
  - `WeakKeyDictionary` requires factory objects to be weakly
    referenceable. Plain functions, methods, and classes all are.
    `functools.partial` is not — if any caller ever registers a
    partial as a factory the cache will fail with `TypeError`
    at registration. Acceptable: this is a strictly better
    failure mode than the silent stale-id bug it replaces.

- **Sibling proposals**:
  - `explicit-router-surface` removes `stage_extra` and the
    `PENDING_EXTRA_ATTR` pattern entirely. This proposal types the
    destination model; the two compose cleanly in either order.
  - `loud-degrade-everywhere` reworks silent-degrade paths in
    middleware. Independent.
