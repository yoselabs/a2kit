# Design — router-class-auto-collect

> Wave 2, BREAKING. Decision record: [ADR 0028](../../../docs/adr/0028-unified-surface-architecture.md)
> decision 7 ("Router authoring: class + auto-collect"), which **amends**
> [ADR 0002](../../../docs/adr/0002-author-annotation-surface.md).
> Model: [`docs/SURFACE_ARCHITECTURE.md`](../../../docs/SURFACE_ARCHITECTURE.md) §6.

## The mechanism: decorator-marker collection

Today the verb decorators (`@a2kit.read/write/list_/tool`) stamp metadata
onto the decorated method, readable via `_get_meta(fn)` (used in
`Router.__init__` at `routers.py:153` today to validate the `tools=`
entries). That marker already **is** the source of truth for "this method
is a tool." The `tools=` tuple is a second, hand-maintained copy of that
same fact.

The change deletes the copy. `Router.__init_subclass__` reads the markers
directly:

```python
def __init_subclass__(cls, **kwargs):
    super().__init_subclass__(**kwargs)
    tools, enrichers = [], []
    for name, attr in vars(cls).items():          # cls.__dict__, NOT dir(cls)
        meta = _get_meta(attr)                     # the marker the decorator stamped
        if meta is None:
            continue
        if meta.is_enricher:                       # @a2kit.enricher
            enrichers.append(attr)
        else:                                       # @a2kit.read/write/list_/tool
            tools.append(attr)
    cls._collected_tools = tuple(tools)
    cls._collected_enrichers = tuple(enrichers)
```

The hook iterates `vars(cls)` (i.e. `cls.__dict__`) and keeps **only**
attributes that carry a verb/enricher marker. Inheritance is handled by
walking the MRO and collecting each class's own marked methods (a
subclass that overrides a base tool wins; a subclass that inherits one
without re-declaring still gets it — exactly the MRO semantics the old
drift check special-cased).

### Why this is NOT the `dir()` walk ADR 0002 rejected

ADR 0002 and the current `Router` docstring (`routers.py:76-79`) reject
"`__init_subclass__` registry, `dir()` walk." Those are two distinct
techniques, and the distinction is the whole point:

| Rejected (magic) | Chosen (marker-driven) |
|---|---|
| `dir(self)` / `vars(cls)` enumerated and **every** callable treated as a tool | `vars(cls)` enumerated, but a method is a tool **only if it carries the decorator marker** |
| Naming-convention collection (`tool_*`, `handle_*`) | No name inspection at all; the `@a2kit.read` on the method is the sole signal |
| The author cannot tell from the method whether it is exposed | The author reads `@a2kit.read` directly above the method — maximal locality |

A `dir()` walk infers intent from *structure* (what methods exist / how
they are named). Marker collection reads an *explicit declaration* the
author wrote on the method. The iteration over `vars(cls)` is an
implementation detail of *finding* the markers; it is not what decides
membership — the marker decides membership. This is the
enterprise-framework norm (Spring `@Component`, Nest `@Get`, .NET
attributes): the decorator is the registration, scanned by the framework.

## Why `__init_subclass__`, not a metaclass

`__init_subclass__` is the minimal hook for "run code when a subclass is
defined." `Router` already uses it (the enricher class-body ban,
`routers.py:101`), so no new machinery is introduced — the existing hook
gains the collection loop. A custom metaclass would:

- introduce a metaclass-conflict risk for any consumer that wants to mix
  `Router` with another metaclassed base,
- be heavier than the problem (we need one class-definition-time pass, not
  custom class *creation* control),
- be less AI-legible (metaclasses are the canonical "here be dragons").

`__init_subclass__` is the lighter, more legible tool and is already in
use. (ADR 0028 decision 7 picks the class form precisely because a2kit's
routers mount **once** under their slug — no app-factory / multi-mount
need that would justify the instance + `@router.read` form.)

## Enricher unification

Today enrichers are a special case: the class-body `enrichers` / `enrich`
shapes are **banned** (raise `TypeError` from `__init_subclass__`,
`routers.py:103-112`), and the only sanctioned form is the
post-construction instance decorator:

```python
router = TasksRouter()
@router.enricher
def on_missing(exc: LookupError) -> TaskNotFound | None: ...
```

That special case exists because, before auto-collect, there was no
class-body channel that wasn't either the banned tuple-shape or `dir()`
magic. Auto-collect removes the reason for the special case: an enricher
is just another `@a2kit`-marked method, collected by the same hook:

```python
class TasksRouter(a2kit.Router):
    slug = "tasks"

    @a2kit.read
    def get_task(self, *, store: TrackerStore, task_id: str) -> Task: ...

    @a2kit.enricher
    def on_missing(self, exc: LookupError) -> TaskNotFound | None: ...
```

Dispatch semantics are unchanged — the first parameter's annotation still
chooses narrow vs wide dispatch; the return contract is still
`AppError | None`; chain order is still per-tool inline → router → app →
defect quarantine. Only the **authoring channel** moves: from the
post-construction instance decorator to the in-class marked method. The
class-body `enrichers`/`enrich` ban can relax (those shapes are no longer
ambiguous with a tuple that no longer exists), but the `@router.enricher`
instance form is retired in favor of the unified marked-method form so
there is exactly one way to declare an enricher.

## How it amends ADR 0002

ADR 0002's load-bearing rejection was of *magic collection* — it called
out `dir()` walks and naming conventions by name and chose the explicit
`tools=` tuple to avoid them. ADR 0028 decision 7 narrows that rejection:
the **objection to magic is upheld**; what changes is the recognition
that decorator-marker collection is *not* magic (the declaration is
explicit and local), and that the tuple it was protecting against
mis-collection has its own, larger cost (duplication + ordering footgun +
a whole drift-detection requirement). The amendment is therefore scoped:

- **Upheld from ADR 0002:** no `dir()`-walk, no naming-convention
  collection, `pydantic.Field` per-parameter surface, the verb-decorator
  per-tool metadata channel.
- **Amended by ADR 0028 decision 7:** the explicit-`tools=`-tuple
  requirement is replaced by `__init_subclass__` decorator-marker
  collection.

A doc task (tasks.md §5) updates ADR 0002's status line to record the
amendment and cross-link ADR 0028 decision 7, so the decision log stays
coherent (the ADR is *amended*, not *superseded* — its core pydantic
decision stands).

## Static derivation survives

The public-API tier snapshot derives the surface statically from the
AST (`public-api-tier-snapshot` capability). Because the verb decorators
remain AST-visible (`@a2kit.read` is a literal decorator node on the
method), removing the runtime `tools=` tuple does not affect static
derivation — the snapshot reads decorators, not the tuple. No regression
to the static-inspectability guarantee.

## Co-ship note

This is the **authoring half** of the Wave 2 breaking surface. It ships
in the same release as:

- `native-tree-homomorphism` — flat `slug_leaf` canonical names +
  `canonical_name_override`,
- `surfaces-projection-axis` — the `{absent,listed,unlisted}` matrix,
- `app-as-peer-root` — `App` becomes a peer class with the same
  marked-method collection (the App-level mirror of this change).

The rename, the new axis, and the new authoring shape are one breaking
surface so consumers (a2atlassian / a2db / a2web) absorb a single
migration rather than three. See `docs/SURFACE_ARCHITECTURE.md` §7
(Wave 2) for the sequencing and dependency notes.
