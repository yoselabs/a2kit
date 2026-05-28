## Why

a2web is the only confirmed a2kit consumer today (per
`docs/PROMOTION_AUDIT.md`). It is about to undergo a substrate-deepening
upgrade. Three small a2kit gaps currently force a2web to carry ~100 LOC
of workarounds. Closing those gaps in a2kit now means the upgrade gets
to *delete* code instead of *port* it, and validates the substrate
against a real consumer's ergonomic pain.

All three changes are additive (no breaking changes), small, and
unblock a2web cleanup independently. Bundled because they share one
release-coordinated motive: prepare the substrate for a2web's handoff.

## What Changes

- **A1 — `exclude_empty=True` formatter flag.** Let a tool's return
  type opt into pruning empty fields (`None` / `[]` / `{}` / `""`) from
  the JSON wire payload. Either a per-return-type formatter option or a
  model-level marker honored by `format_response`. Removes a2web's
  custom `_prune_wire` workaround (~90 LOC across `AskResponse` and
  `FetchResponse`'s `@model_serializer(mode="wrap")` decorators).
- **A2 — Runtime tool selection at server start.** First-class env-var
  + CLI flag (`--tools=<comma-list>`) intercepted before
  `build_mcp_server(app)`. Exposes a tool subset on MCP/CLI surfaces
  without code changes. Complements the existing compile-time
  `visibility=` decorator kwarg. Removes a2web's `ask_only: bool`
  setting + constructor-time `WebRouter.tools` rebuild.
- **A3 — Promote `a2kit.Lazy` and `a2kit.LddEmission` to top-level
  re-exports.** Both already live in `a2kit.packages.di.Lazy` /
  `a2kit.packages.ldd.LddEmission`. The latter are sink-author /
  tool-seam surfaces that consumers touch often;
  `a2kit.packages.*` reads as internal scaffolding. Document
  `a2kit.packages.*` as private (stdlib `_thread` / `threading`
  convention).

All three are tracked in `~/Workspaces/a2web/docs/history/A2KIT_WISHES_DEFERRED.md`
(rounds 10-12). Article VI Magic Budget check: ≤2 new consumer-facing
concepts (A1 adds 1 flag, A2 adds 1 selector mechanism, A3 adds 0 — it
relocates existing). PASS.

## Capabilities

### New Capabilities
- `runtime-tool-selection`: First-class server-start tool-subset
  selector. Env var (`A2KIT_TOOLS=<comma-list>`) + CLI flag
  (`--tools=<comma-list>` on `serve` and CLI sub-apps). Intercepted
  during `build_mcp_server` / CLI build; filters the descriptor set
  before each surface registers tools. Complements compile-time
  `visibility=`; orthogonal to auth-time gating.

### Modified Capabilities
- `type-driven-format-routing`: Adds opt-in empty-field pruning. A
  return type may carry a `formatter_options` marker (or call
  `model_dump` with the new flag) to drop None/[]/{}/'' fields from
  the JSON payload. Default behavior unchanged (additive).
- `thin-core-surface`: `Lazy[T]` and `LddEmission` graduate to
  `a2kit.Lazy` / `a2kit.LddEmission` top-level re-exports. Old
  `a2kit.packages.di.Lazy` / `a2kit.packages.ldd.LddEmission` paths
  remain as private aliases (no removal — they re-export the canonical
  top-level symbols).

## Impact

- Affected code: `src/a2kit/packages/formatter/`, `src/a2kit/packages/serve.py`,
  `src/a2kit/packages/cli/builder.py`, `src/a2kit/packages/mcp/server.py`,
  `src/a2kit/__init__.py`.
- New tests: per-spec scenario coverage under
  `tests/capabilities/runtime_tool_selection/` (new directory) and
  augmentations to `tests/capabilities/type_driven_format_routing/`.
- Constitution articles applied:
  - Article VI (Magic Budget) — ≤2 new concepts: A1=1, A2=1, A3=0 → PASS
  - Article V (Substrate Refusal) — explicit decision NOT to add the
    `a2kit.desc()` sugar wish from the same v0.41 wish list (killed by
    Article VI's pydantic-sacred clause)
  - Article VII (Decisions Recorded) — this proposal cites both
- No dependency changes (Article VIII / IX N/A — internal additions).
- No breaking API changes. Existing consumers see no behavioral diff
  unless they opt into the new flag / selector.
- Wire-format compatibility: A1 default behavior emits the same JSON
  as today; pruning only fires when explicitly opted in.
- a2web's downstream cleanup is tracked separately in a2web's own
  changelog after this lands.
