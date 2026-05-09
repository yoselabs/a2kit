## Why

After v0.20 the core is small but still leaks four feature-specific concerns into the verb decorators and `A2KitMeta`: enrichment, listview, reporting, and composition slugs. Plus `WriteNotAllowed.connection_key` keeps the word "connection" inside `src/a2kit/exceptions.py`. To a senior Python reviewer these read as accumulated framework magic — the kind of "AI slop" surface where every feature parks a kwarg on the central decorator. Round 2 finishes the cut: `src/a2kit/*.py` should mention no domain feature by name. Each feature lives in its own package, attaches via stacked decorators that write into `A2KitMeta.extra`, and adapters read from there at registration time.

## What Changes

- **BREAKING**: `@a2kit.read/@write/@list_/@tool` lose their `enricher=`, `list_view=`, `router_slug=`, `report=` kwargs. The core decorator's only kwargs are `name`, `tags`, `annotations`.
- **BREAKING**: `A2KitMeta` loses dedicated fields for `enricher`, `list_view`, `report_type`, `report_schema`, `router_slug`. Features write namespaced keys into `A2KitMeta.extra` (e.g. `extra["a2kit.enricher"] = fn`).
- **BREAKING**: Move `WriteNotAllowed` from `a2kit.exceptions` to `a2kit.packages.connections.exceptions`. `src/a2kit/*.py` has zero references to "connection" or "enricher".
- **BREAKING**: Drop Router slug auto-derivation. No more "TasksRouter" → "tasks" magic. Router slug = `name=` arg, or `name` class attr, or `type(self).__name__` verbatim. Reviewers can no longer ask "where did this slug come from?"
- New stacked-decorator API in feature packages:
  - `a2kit.packages.enrichers.enriches(fn)(tool)` — stamps `extra["a2kit.enricher"]`
  - `a2kit.packages.mcp.lists(...)` — stamps `extra["a2kit.list_view"]`
  - `a2kit.packages.mcp.reports(ReportT)` — stamps `extra["a2kit.report_type"]`, computes schema lazily inside the package
- Routers store **bound methods** instead of class-dict raw functions. `_bind_if_method` deleted. `_collect_methods` switches from `type(self).__dict__` walk to `inspect.getmembers(self)` filtering by `getattr(m, '_a2kit', None)`.
- CLI builder drops `_wrap_main_with_app_ctx` monkey-patch and the `_APP_CTX` ContextVar. Lazy `serve` and `--no-reports/--no-events` handlers close over `app` directly via the per-app build call.
- New lint rules:
  - `A2K-CORE-CLEAN`: `src/a2kit/*.py` (excluding `packages/`) cannot grep-match `connection`, `enricher`, `list_view`, `report_type`, `report_schema`, `router_slug` outside of `metadata.extra` access.
  - `A2K-EXTRA-NAMESPACE`: keys written to `A2KitMeta.extra` must start with `a2kit.` (registered prefix) or a dotted-package prefix.
- Pydantic schema generation moves out of `tool.py` into `packages/mcp/reports.py` (or wherever `reports(...)` lives).
- `_slugify` deleted. Router naming becomes a 3-line lookup.

Migration: a one-shot codemod for example/tests rewrites `@a2kit.read(enricher=X, list_view=Y, report=Z)` → stacked decorators. Public API rename surface is small; tracker example + tests cover the full migration.

## Capabilities

### New Capabilities
- `core-purity`: invariants that constrain `src/a2kit/*.py` (excluding `packages/`) — no domain feature names, no monkey-patching, no class-dict scanning, no slug derivation. Verified by lint.

### Modified Capabilities
None — no archived spec under `openspec/specs/` yet (prior changes still in-progress). Verb decorator + Router slug requirements land as ADDED in `core-purity`.

## Impact

- **Public API breakage**: every existing tool decorated with `enricher=`, `list_view=`, `report=`, or `router_slug=` must move to stacked decorators. Tracker example and ~10 test sites affected. No external users yet (v0.20 just shipped).
- **Internal refactor**: `tool.py` shrinks (~60 → ~30 lines); `metadata.py` simplifies (drops 4 fields); `routers.py` drops the enricher wrap loop; `builder.py` drops `_bind_if_method` and `_wrap_main_with_app_ctx`.
- **New code**: 3 small feature decorators (`enriches`, `lists`, `reports`) totalling ~80 lines across their respective packages.
- **Dependencies**: pydantic import moves from core to `packages/mcp` (already a dependency there). No new deps.
- **Lint coverage**: 2 new static rules. `A2K-CORE-CLEAN` is grep-based on imports + identifier use. `A2K-EXTRA-NAMESPACE` is a single-pass AST visitor.
- **Cold-start**: should improve marginally (pydantic no longer imported at decorator definition). Target: stay ≤15ms.
- **Coverage**: gate stays at 92%. Net LOC change estimated −150.
