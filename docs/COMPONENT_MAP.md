# Component Map

Auto-generated from the layer manifest (`src/a2kit/packages/lint/layers.py`)
and the parsed `src/a2kit/` import graph by `scripts/component_map.py`. Do
not edit by hand — regenerate with `make component-map` (the pre-commit
hook enforces freshness).

This is the agent-loadable view of a2kit's internal dependency DAG, the
structural sibling of `docs/adr/INDEX.md`. A unit may import only
strictly-lower layers; the `A2K-LAYER` lint rule enforces it. Edges to
the foundational leaf modules (`a2kit.exceptions`,
`a2kit._context_protocol`) are layer-exempt and omitted here, matching
the lint's own view of the graph.

## Units

| Unit | Layer | Files | Fan-in | Fan-out | Depends on |
|------|-------|-------|--------|---------|------------|
| `context` | 0 | 1 | 3 | 0 | — |
| `di` | 0 | 9 | 3 | 0 | — |
| `formatter` | 0 | 7 | 5 | 0 | — |
| `health` | 0 | 1 | 2 | 0 | — |
| `ldd` | 0 | 1 | 1 | 0 | — |
| `lint` | 0 | 18 | 0 | 0 | — |
| `kernel` | 1 | 6 | 6 | 0 | — |
| `authoring` | 2 | 6 | 6 | 3 | `di`, `formatter`, `kernel` |
| `runtime` | 3 | 3 | 4 | 6 | `authoring`, `di`, `formatter`, `health`, `kernel`, `ldd` |
| `connections` | 4 | 8 | 0 | 2 | `authoring`, `di` |
| `dispatch` | 4 | 4 | 2 | 4 | `authoring`, `context`, `kernel`, `runtime` |
| `cli` | 5 | 6 | 0 | 8 | `authoring`, `context`, `dispatch`, `formatter`, `health`, `kernel`, `mcp`, `runtime` |
| `codemode` | 5 | 4 | 1 | 0 | — |
| `mcp` | 5 | 7 | 2 | 6 | `authoring`, `codemode`, `dispatch`, `formatter`, `kernel`, `runtime` |
| `otel` | 5 | 3 | 0 | 0 | — |
| `testing` | 6 | 6 | 0 | 6 | `authoring`, `context`, `formatter`, `kernel`, `mcp`, `runtime` |

## Layer-ordered DAG

### Layer 0

- `context` → no cross-unit dependencies
- `di` → no cross-unit dependencies
- `formatter` → no cross-unit dependencies
- `health` → no cross-unit dependencies
- `ldd` → no cross-unit dependencies
- `lint` → no cross-unit dependencies

### Layer 1

- `kernel` → no cross-unit dependencies

### Layer 2

- `authoring` → `di`, `formatter`, `kernel`

### Layer 3

- `runtime` → `authoring`, `di`, `formatter`, `health`, `kernel`, `ldd`

### Layer 4

- `connections` → `authoring`, `di`
- `dispatch` → `authoring`, `context`, `kernel`, `runtime`

### Layer 5

- `cli` → `authoring`, `context`, `dispatch`, `formatter`, `health`, `kernel`, `mcp`, `runtime`
- `codemode` → no cross-unit dependencies
- `mcp` → `authoring`, `codemode`, `dispatch`, `formatter`, `kernel`, `runtime`
- `otel` → no cross-unit dependencies

### Layer 6

- `testing` → `authoring`, `context`, `formatter`, `kernel`, `mcp`, `runtime`
