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
| `context` | 0 | 3 | 6 | 1 | `ldd` |
| `di` | 0 | 11 | 6 | 0 | — |
| `formatter` | 0 | 9 | 6 | 0 | — |
| `health` | 0 | 2 | 3 | 1 | `di` |
| `ldd` | 0 | 5 | 2 | 0 | — |
| `lint` | 0 | 20 | 0 | 0 | — |
| `select` | 0 | 2 | 2 | 0 | — |
| `kernel` | 1 | 6 | 4 | 0 | — |
| `authoring` | 2 | 6 | 6 | 3 | `di`, `formatter`, `kernel` |
| `runtime` | 3 | 3 | 6 | 8 | `authoring`, `context`, `di`, `formatter`, `health`, `kernel`, `ldd`, `select` |
| `connections` | 4 | 9 | 0 | 3 | `authoring`, `di`, `runtime` |
| `dispatch` | 4 | 6 | 3 | 5 | `authoring`, `context`, `di`, `kernel`, `runtime` |
| `cli` | 5 | 6 | 0 | 7 | `authoring`, `context`, `dispatch`, `formatter`, `health`, `mcp`, `runtime` |
| `codemode` | 5 | 5 | 1 | 1 | `formatter` |
| `http` | 5 | 3 | 0 | 5 | `context`, `di`, `dispatch`, `health`, `runtime` |
| `mcp` | 5 | 9 | 2 | 8 | `authoring`, `codemode`, `context`, `dispatch`, `formatter`, `kernel`, `runtime`, `select` |
| `otel` | 5 | 3 | 0 | 0 | — |
| `testing` | 6 | 7 | 0 | 5 | `authoring`, `context`, `formatter`, `mcp`, `runtime` |

## Layer-ordered DAG

### Layer 0

- `context` → `ldd`
- `di` → no cross-unit dependencies
- `formatter` → no cross-unit dependencies
- `health` → `di`
- `ldd` → no cross-unit dependencies
- `lint` → no cross-unit dependencies
- `select` → no cross-unit dependencies

### Layer 1

- `kernel` → no cross-unit dependencies

### Layer 2

- `authoring` → `di`, `formatter`, `kernel`

### Layer 3

- `runtime` → `authoring`, `context`, `di`, `formatter`, `health`, `kernel`, `ldd`, `select`

### Layer 4

- `connections` → `authoring`, `di`, `runtime`
- `dispatch` → `authoring`, `context`, `di`, `kernel`, `runtime`

### Layer 5

- `cli` → `authoring`, `context`, `dispatch`, `formatter`, `health`, `mcp`, `runtime`
- `codemode` → `formatter`
- `http` → `context`, `di`, `dispatch`, `health`, `runtime`
- `mcp` → `authoring`, `codemode`, `context`, `dispatch`, `formatter`, `kernel`, `runtime`, `select`
- `otel` → no cross-unit dependencies

### Layer 6

- `testing` → `authoring`, `context`, `formatter`, `mcp`, `runtime`
