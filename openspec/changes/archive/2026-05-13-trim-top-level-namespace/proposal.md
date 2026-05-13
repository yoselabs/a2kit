# Trim top-level `a2kit.*` namespace

## Why

The audit (explore session 2026-05-13) enumerated the public top-level
exports. Of 22 names, the front-door surface for the 95% author flow
is ~7. The other 15 are introspection / sink-author / advanced-DI /
exception-class surface that inflates every IDE autocomplete a
consumer sees.

Concrete inventory:

```
KEEP at top-level (95% surface):
  App, Router, run, read, write, list_, tool,
  ToolContext, HealthResult, A2KitError, Surface→Visibility (LiteralAlias)

DEMOTE to owning modules (still importable; just not top-level):
  A2KitMeta                          → a2kit.metadata.A2KitMeta
  RouterRegistry                     → a2kit.routers.RouterRegistry
  UNRESOLVED                         → a2kit.app.UNRESOLVED
  ToolCallContamination              → a2kit.exceptions.*
  InvalidToolReturnTypeError         → a2kit.exceptions.*
  InvalidFilterExpression            → a2kit.exceptions.*
  ReportTypeNotDeclared              → a2kit.exceptions.*
  ReportTypeMismatch                 → a2kit.exceptions.*
```

Plus four LDD names demoted from the `a2kit.ldd` re-export to a new
sink-author submodule `a2kit.ldd.sinks`:

```
DEMOTE from a2kit.ldd (still in a2kit.ldd.sinks):
  LddEmission, LddSink, format_ldd_line, ldd_state_for_call
```

Each demoted symbol is **still importable** from its owning module.
Only the convenience top-level re-export is removed. The cold-start
path is unaffected (these were already lazy-imported via
`_LAZY_ATTRS`).

## What changes

- **REMOVE** from `src/a2kit/__init__.py` `_LAZY_ATTRS` and `__all__`:
  `A2KitMeta`, `RouterRegistry`, `UNRESOLVED`,
  `ToolCallContamination`, `InvalidToolReturnTypeError`,
  `InvalidFilterExpression`, `ReportTypeNotDeclared`,
  `ReportTypeMismatch`.
- **KEEP** `A2KitError` at top-level (the umbrella exception is the
  one most likely to be caught by application-level handlers).
- **MOVE** `LddEmission`, `LddSink`, `format_ldd_line`,
  `ldd_state_for_call` out of `src/a2kit/ldd.py` re-exports.
  Authors who need them import from
  `a2kit.packages.ldd` directly. Optionally create a thin
  `a2kit.ldd.sinks` submodule that re-exports those four; defer the
  decision to implementation time based on consumer feedback.
- **DOCUMENT** the new front-door surface in the README / ADR
  prescription.

## Non-goals

- Removing any symbol from its owning module — pure demotion.
- Changing `App` / `Router` / `run` / decorator entry points.
- Touching the `a2kit.ldd` event/report/log primitives (those are
  the live author surface; only the sink-author types are demoted).
- Renaming `a2kit.testing.app` (deferred; possibly confusing with
  `a2kit.App`, but cheap separate change if needed).

## Migration

Mechanical import-line replacement for each demoted symbol:

```python
# before
from a2kit import A2KitMeta, RouterRegistry, UNRESOLVED, ToolCallContamination

# after
from a2kit.metadata import A2KitMeta
from a2kit.routers import RouterRegistry
from a2kit.app import UNRESOLVED
from a2kit.exceptions import ToolCallContamination
```

In-repo: 2 test sites for `UNRESOLVED`, 1 for `A2KitMeta`, none for
`RouterRegistry`, ~5 for the demoted exceptions (test handlers).
Downstream: grep on release.

## Risk

S. Breaking change but mechanically migratable. The lint rule update
catches stragglers at lint time.
