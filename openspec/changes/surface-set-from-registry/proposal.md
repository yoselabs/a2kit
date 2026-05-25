## Why

The Surface Protocol refactor (ADR 0020 + the `add-surface-protocol-additive`
change) made `SURFACE_REGISTRY` the canonical registry of mounted
surfaces — every substrate adapter (MCP, HTTP, future A2A / gRPC)
self-registers, and `SURFACE_REGISTRY.names()` already exposes the
list. But the verb decorators still hardcode the surface set:

```python
# src/a2kit/_verbs.py:111
allowed = frozenset({"mcp", "api"})
```

When `expose=` is validated against this literal, adding a new transport
requires editing `_verbs.py`. The lint layer can't catch this because
the literal isn't an import. The audit found this as the cleanest
"the seam moved" symptom: composition exists at the registry level,
coupling remains at the decoration level.

## What Changes

- Replace the hardcoded `frozenset({"mcp", "api"})` in
  `src/a2kit/_verbs.py` with a runtime read of
  `SURFACE_REGISTRY.names()`.
- Adjust error messages on `expose=` validation to enumerate from the
  registry (e.g. `Allowed surfaces: ('mcp', 'api')` is computed, not
  literal).
- Resolve the layer-DAG question: `_verbs.py` is in the `authoring` core
  sub-unit (L2); `SURFACE_REGISTRY` lives under
  `a2kit.packages.dispatch.surface` (L4). Authoring importing from L4
  is upward — a violation. Resolution: introduce a tiny L0 "surface
  name registry" leaf module (e.g. `a2kit.packages.dispatch.names` or
  collapse names into a kernel-layer helper) that both authoring and
  dispatch import from. Decided in design.md.
- Tests cover: (a) registering a third synthetic surface makes its name
  valid in `expose=`, (b) the error message lists currently-registered
  surfaces.

## Capabilities

### Modified Capabilities

- `verb-decorators`: `expose=` accepts any registered surface name, not
  a fixed literal set.
- `surface-protocol`: `SURFACE_REGISTRY.names()` is documented as the
  source of truth that `expose=` validation consults.

## Impact

- Affected code: `src/a2kit/_verbs.py`, possibly a new small module in
  `src/a2kit/packages/dispatch/` (depending on layer resolution),
  `src/a2kit/packages/lint/layers.py` (may need to acknowledge the new
  leaf module).
- API: none for consumers; the set of valid `expose=` values is
  data-driven now.
- Dependencies: none.
- Tests: extend verb-decorator tests to cover dynamic surface registry.
- Future-proofing: a future transport (gRPC, AsyncAPI, etc.) becomes a
  one-file landing — register a Surface implementation; verbs accept
  the name automatically.
