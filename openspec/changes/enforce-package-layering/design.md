## Context

`decouple-import-cycles` makes the graph acyclic; this change keeps it
that way. The framework already has the lint machinery
(`packages/lint/rules/importing.py` hosts `A2K-IMPORT-DISCIPLINE` and
`A2K-PKG-INIT-IMPORT`). What is missing is a *layer* concept, *core*
modelled as a layer, and front-door enforcement.

ADR 0004 tiers the *public Python surface* by audience. This change is
the internal sibling: tiering the *dependency graph* by layer.

## Goals / Non-Goals

**Goals**

- A regression — a new cycle (runtime or type-only), a new
  higher-layer import, a new past-the-front-door import — fails
  `make lint`.
- Each `packages/*/__init__.py` is the enforced sole entry point from
  outside the package.

**Non-Goals**

- Not re-architecting any package — this change adds gates and rewrites
  import lines to satisfy them.
- Not touching the `A2K-IMPORT-DISCIPLINE` fastmcp allowlist.
- Not layering the core top-level modules *against each other* — core
  is one unit in the manifest; intra-core ordering is out of scope.

## Decisions

### D1. Core is a layer, not an exempt zone

The worst cycle the review found — `app.py ↔ packages/health` — spans
the core boundary. A layer model covering only `packages/*` is blind to
it by construction. So the manifest includes a `core` pseudo-unit (all
top-level `a2kit.*` modules) at L2: above the kernel packages it
imports (`di`, `formatter`, `ldd`, `health`), below the packages that
import it (`connections`, the transports). `A2K-LAYER` resolves every
import to its unit — core or a named package — and applies the same
rule uniformly.

### D2. The rule inspects `TYPE_CHECKING` imports

The `app ↔ health` cycle hid inside a `TYPE_CHECKING`-guarded
`from a2kit.app import App`. A rule that only walked runtime imports
would have declared the graph clean. `A2K-LAYER` walks all
`ast.ImportFrom` nodes regardless of guard. A type-only cycle is still
a comprehension cycle and still constrains refactoring.

### D3. Layers are integers in one manifest, not folders

A flat `dict[str, int]` manifest in `packages/lint/`. Moving a unit
between layers is a one-line edit. Folder-nesting by layer would be a
churn-heavy restructure for no extra safety.

### D4. `connections` and `dispatch` share L3

`connections` imports core (`a2kit.app`, `a2kit.signature`, both
`TYPE_CHECKING`) and `di`; it is imported by `cli`. `dispatch` (added
by `extract-dispatch-pipeline`) imports core, `ldd`, and `context`, and
is imported by both `cli` and `mcp`. Both are neither kernel nor
transport — they sit above core, below the transports. They do not
import each other, so sharing L3 is consistent with the same-layer
no-cycle rule.

### D5. Front-door rule has an allowlist, not zero exceptions

Some deep imports may be legitimate. `A2K-PKG-FRONT-DOOR` ships with a
documented allowlist constant, mirroring `A2K-IMPORT-DISCIPLINE`'s
`_FASTMCP_ALLOWLIST`. The default is empty; every entry needs a
comment.

### D6. Warn-first, then flip — the proven rollout

`A2K-CORE-CLEAN` (de-magic-2) shipped warn-only, source was cleaned,
then it flipped to hard error. Same here: the rules cannot flip until
`decouple-import-cycles` has landed and `app.py` / `signature.py` /
`tool.py` are rewritten onto the front doors.

### D7. Re-exports are the front door, not a layout violation

`module-layout-discipline` requires `__init__.py` files "minimized to
package boundaries". Explicit public re-exports in `di/__init__.py` /
`formatter/__init__.py` *are* the package boundary — the declared
public API. This is consistent with that requirement, not in tension
with it; the MODIFIED requirement states so explicitly.
