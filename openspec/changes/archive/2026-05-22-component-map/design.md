## Context

The layer manifest in `packages/lint/layers.py` is the single source of truth for unit-to-layer assignment, and `A2K-LAYER` enforces the import rules. But the *shape* of the graph — who depends on whom, which unit is a chokepoint — is invisible without manually parsing imports. `scripts/adr_index.py` already solves the analogous problem for ADRs: a generator reads structured source, emits `docs/adr/INDEX.md`, and a pre-commit hook keeps it current. This change applies the same proven pattern to the component graph.

## Goals / Non-Goals

**Goals:**

- A generated `docs/COMPONENT_MAP.md` that is always current and loadable in one read.
- The generator reads `layers.py` as the source of truth — no second manifest.
- A pre-commit staleness gate, mirroring `adr-index`.

**Non-Goals:**

- New import enforcement. `A2K-LAYER` already gates imports; this is a view.
- A graphical / SVG rendering. Markdown only, for agent-loadability.
- Analyzing anything beyond `src/a2kit/` (no test or example graph).

## Decisions

**1. Output is `docs/COMPONENT_MAP.md`, markdown, agent-loadable.**
It sits beside `docs/adr/INDEX.md` as the second agent-loadable architecture entry point. Content: a unit table (unit, layer, file count, dependencies, fan-in / fan-out) and a layer-ordered DAG rendering. The same data computed during the explore session that produced this change.

**2. The generator reuses `layers.py` directly.**
`scripts/component_map.py` imports `LAYER_MANIFEST`, `unit_for_path`, and `layer_of` from the manifest module rather than re-deriving unit assignment. The manifest stays the single source of truth; the map is a pure projection of it plus the parsed import graph.

**3. Regeneration is a pre-commit staleness gate, not a runtime artifact.**
The `make component-map` target writes the file; a pre-commit hook regenerates and fails if the working copy differs — identical to `adr-index`. No build-time or import-time cost.

## Risks / Trade-offs

- **The map drifts if the hook is skipped** → the staleness gate fails any commit where the file is out of date; this is the same guarantee `adr-index` already relies on. Mitigation: model the hook on the existing `adr-index` hook exactly.
- **Ordering against `split-app-runtime`** → if `component-map` lands first, its initial map shows the single `core` unit; once `split-app-runtime` archives, the next regeneration shows `kernel` / `authoring` / `runtime`. No code coupling — the generator reads whatever the manifest says. Either order is safe.
