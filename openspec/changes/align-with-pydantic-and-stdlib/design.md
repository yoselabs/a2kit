# Design — align-with-pydantic-and-stdlib

## Context

The three items below were surfaced by a focused "what shims could
we delete without losing capability?" audit. Each is independent at
the implementation level; we group them because the narrative is
shared (trust pydantic / stdlib) and the spec impact is co-located.

## Decisions

### D-PARAM-DROP — `a2kit.Param` is removed outright

`Param(description=, **extras)` calls `pydantic.Field(description=, **extras)`
verbatim and returns a `FieldInfo`. There is no value the wrapper
adds — pydantic already supports `Annotated[T, Field(description="...")]`,
the MCP schema builder (FastMCP) already reads it, the CLI builder
already reads it via `description_of`. The wrapper exists only
because a previous round of consumer feedback asked for a name that
read like "this is a tool parameter, not a body-model field" — a
cosmetic preference, not a capability gap.

**Decision**: remove. Pre-1.0 surface, two-version-old addition,
zero external consumers known. The migration is `pydantic.Field(description="...")`.

Alternatives considered:
- **Keep `Param` as a thin alias, deprecate, remove in v0.31.** Rejected:
  noise without benefit. The codebase has no SemVer commitment yet
  and the migration is a single regex.
- **Keep `Param` and add real capability** (e.g., a custom
  `FieldInfo` subclass carrying CLI-specific metadata like
  `cli_short_flag="u"`). Rejected as scope creep; if and when CLI-only
  metadata is needed, it lives in a new marker class with a different
  name, not by re-inflating `Param`.

`description_of(annotation)` stays — it's the small internal utility
that scrapes `FieldInfo.description` from `typing.get_args(...)`. It
moves to **`src/a2kit/_field_introspect.py`** (new private module).
`params.py` is deleted outright, not renamed: a single-symbol module
named after a removed concept ("params") is confusing and the
leading-underscore name correctly signals "internal introspection
helper, not the public face of any parameter surface." Imports in
`src/a2kit/packages/mcp/schema.py` and
`src/a2kit/packages/cli/builder.py` (the two known consumers) update
to `from a2kit._field_introspect import description_of`.

### D-EXTRAS-TYPED — `A2KitMeta.extras: A2KitMetaExtras` (pydantic BaseModel)

The known keys today and their final attribute names:

| Old string key            | New attribute      | Type                       |
|---------------------------|--------------------|----------------------------|
| `a2kit.report_type`       | `report_type`      | `type \| None`             |
| `a2kit.report_schema`     | `report_schema`    | `dict[str, Any] \| None`   |
| `a2kit.router_slug`       | `router_slug`      | `str \| None`              |
| `a2kit.surfaces`          | `surfaces`         | `Surface \| None`          |
| `a2kit.list_view`         | `list_view`        | `ListViewSettings \| None` |

`A2KitMetaExtras` is a `BaseModel` not a `dataclass` because:
- It needs `arbitrary_types_allowed=True` for `type` and `Surface`;
  pydantic handles this with one `model_config` line.
- Future extras may want validation (e.g., `report_type` must be a
  pydantic model or a scalar-or-list-of-pydantic-model); pydantic
  validators are the right hook.
- Pydantic is already a hard dependency.

`A2KitMeta` remains `@dataclass(frozen=True, slots=True)`. The
`extras` field defaults to `A2KitMetaExtras()` via `field(default_factory=...)`.

`stage_extra(fn, key, value)` is reshaped to take an attribute name
(no string-key translation) and `setattr` it on the typed model. The
sibling `explicit-router-surface` proposal removes `stage_extra`
entirely; until then it is a one-line setattr.

Alternative considered: **inline the extras fields into `A2KitMeta`
itself** (no nested `extras` namespace). Rejected because `A2KitMeta`
has a stable surface contract (tool_name, verb, tags, annotations,
context_param_name) and the "extras" name correctly signals "open
extension point for verb decorators and routers to stamp." Future
extras shouldn't require touching the core `A2KitMeta` declaration.

Cost: every tool decoration runs `A2KitMetaExtras()` once. Pydantic
BaseModel construction is ~5µs. For a 100-tool app this adds 500µs
to startup. Acceptable; decoration is one-shot.

### D-WIRE-PROJECTION — Wire serialization moves to the MCP transport layer, not onto `meta.extras`

Audit of `extra` consumers surfaced two sites that the original
reader inventory missed:

1. **`src/a2kit/packages/otel/middleware.py:83`** — `extra.get("a2kit.router_slug")`.
   Reads the **wire-projection dict** (`meta_a2kit`, produced by
   `_meta_to_dict`), not the live `A2KitMeta`. Pure read; migrates
   along with the wire-projection rewrite.
2. **`src/a2kit/packages/mcp/server.py:43-45`** — **mutates**
   `extra["a2kit.list_view"] = asdict(list_view)` inside
   `_meta_to_dict`. This is the only mutating "reader" in the codebase.

The mutation forced a choice. Two options:

- **Option (a)**: mutation becomes
  `meta.extras.list_view_wire = list_view.model_dump()` — keep
  the mutation, just type it. Pollutes the typed model with a
  wire-shape twin of `list_view`. Two fields representing the same
  semantic value, divergence risk.

- **Option (b)** *(chosen)*: wire serialization is the wire
  layer's job. `_meta_to_dict` is *that* layer. It calls
  `meta.extras.model_dump(mode="json", exclude={"report_type"})`
  to produce a JSON-safe dict; the typed `meta.extras` is never
  mutated. `list_view`'s `BaseModel.model_dump()` already handles
  the asdict conversion. `report_type` (a `type` object, not
  JSON-safe) is excluded via `model_dump(exclude=...)` rather than
  via the legacy `_EXTRA_DROP_FROM_WIRE` string-key filter, which
  consequently disappears.

Implication: `_meta_to_dict` is rewritten end-to-end; lines 43-45's
mutating shape vanishes; `_EXTRA_DROP_FROM_WIRE` (declared L27,
used L41) deletes; the dataclass-`asdict` branch on L44 deletes
(BaseModel handles its own dump).

Verification grep (run during this revision):

```
$ grep -rn "_EXTRA_DROP_FROM_WIRE\|EXTRA_DROP_FROM_WIRE" \
    /Users/iorlas/Workspaces/a2kit/src /Users/iorlas/Workspaces/a2kit/tests
src/a2kit/packages/mcp/server.py:27:_EXTRA_DROP_FROM_WIRE = ("a2kit.report_type",)
src/a2kit/packages/mcp/server.py:41:    for key in _EXTRA_DROP_FROM_WIRE:
```

Two hits, both inside `_meta_to_dict`. No test references. The
constant is **live but localized**; its only purpose is the
`type`-object exclusion, which `model_dump(exclude={...})`
subsumes. Task §2.8 is therefore "remove", not "rewrite caller."

### D-WEAKCACHE — `_param_cache: WeakKeyDictionary[Factory, list[_ParamSpec]]`

The bug class is documented in `src/a2kit/signature.py`'s design
note. CPython recycles `id(...)` values when refcount drops to zero;
in nested test scopes a factory defined and discarded inside one
test produces an id that the next test's factory may inherit, so the
container reads back a stale `_ParamSpec` list and applies the wrong
signature.

`weakref.WeakKeyDictionary` solves both problems:
- The key is the live factory object, not its id. No aliasing.
- When the factory is garbage-collected the entry vanishes. No
  memory growth across test runs.

Constraint: factories must be weak-referenceable. Plain `def`
functions and classes are. `functools.partial`, `lambda` bound to a
strongly-referenced closure, and builtins-bound callables may not be.
The container today registers `factory or type_` — both branches
produce weak-referenceable objects in every code path we ship.

If a downstream consumer registers a `functools.partial` as a
factory, the cache write will raise `TypeError`. The container can
fall back to "do not cache; introspect fresh each time" with a
warning, or it can document the constraint. Decision: **document
the constraint, do not silently fall back** — the silent-fallback
path is exactly the kind of degrade the sibling
`loud-degrade-everywhere` proposal is removing.

Alternatives considered for the cache-key problem:

- **(a) `id(factory)`-keyed cache (status quo, broken)** — the
  current implementation. Rejected: documented stale-cache hazard
  under CPython id recycling; `signature.py` already records this
  same bug class for the sibling tool-signature cache.
- **(b) `WeakKeyDictionary[Factory, ...]` (chosen)** — keys on the
  live object; entries auto-vacate on GC; no aliasing; no memory
  growth across test runs. Requires factories to be weakly
  referenceable (all current call paths satisfy this).
- **(c) Cache invalidation on `register`** — flush the cache entry
  for any factory replaced via `register()`. Rejected: doesn't
  help when factories are discovered transitively through provider
  chains and never re-registered; the stale-id hit happens between
  two unrelated factories that share an id, neither of which
  triggers the other's invalidation.
- **(d) No cache at all** — introspect parameters fresh every
  resolve. Rejected: parameter introspection sits in the hot DI
  resolution path; profile data shows the cached fast-path is
  hit on every request. Pay-once-per-factory is the right
  granularity.
- **(e) Per-resolve cache** keyed by `Container` instance + factory
  id. Rejected: doesn't solve aliasing because the test container
  reuses a single Container.

## Risks

- **R1 risk**: any downstream tool that imports `a2kit.Param` breaks
  on upgrade. Pre-1.0 acceptable; `Param` will be cited in the
  CHANGELOG BREAKING section with the one-line migration.
- **R4 risk**: the lint rule `rule_purity` reads extras key strings;
  if it isn't updated in the same change, lint becomes either
  silently always-pass (no strings to match) or noisy (false
  positives from typed access). Mitigation: include the rule update
  in the implementation scope, even though the bigger purity rework
  is the sibling proposal's territory.
- **R12 risk**: a real-world factory registration with
  `functools.partial` exists somewhere we haven't grep'd. Mitigation:
  the failure mode is a clear `TypeError` at `register()` time, not
  silent data corruption, and the message tells the consumer to use
  a `def`-bound wrapper instead.

## Migration

- `a2kit.Param("desc")` → `pydantic.Field(description="desc")`
- `a2kit.Param(description="desc")` → `pydantic.Field(description="desc")`
- `a2kit.Param(description="desc", examples=[...])` → `pydantic.Field(description="desc", examples=[...])`
- `meta.extra.get("a2kit.report_type")` → `meta.extras.report_type`
- `meta.extra.get("a2kit.surfaces", Surface.ALL)` → `meta.extras.surfaces or Surface.ALL`
- `meta.extra["a2kit.router_slug"]` → `meta.extras.router_slug`
- No migration needed for the WeakKeyDictionary change — internal only.

### v0.31.0 bundle

Bundled into **v0.31.0** with sibling proposals
`explicit-router-surface` and `lifespan-over-lifecycle-hooks`.
All three are breaking and ship together to keep the migration
to a single upgrade event. No codemod, no shim — users
hand-rewrite call sites; the rewrites are mechanical.

## Sibling proposals (coordination, not scope)

- **`explicit-router-surface`** removes `stage_extra` and the
  `PENDING_EXTRA_ATTR` two-phase staging dance entirely. This
  proposal types the destination model; the two compose cleanly.
- **`loud-degrade-everywhere`** reworks silent-degrade paths in
  middleware and lint rules. Independent of this proposal.

## Open Questions

- **Q1**: Should `description_of` be promoted to a public
  `a2kit._field_introspect.description_of` and documented? It's
  consumed by both MCP and CLI builders internally. Recommendation:
  leave it private; the public contract is "use `pydantic.Field`,
  a2kit picks up the description."
