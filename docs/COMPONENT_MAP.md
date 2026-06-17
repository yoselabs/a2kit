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
| `context` | 0 | 4 | 8 | 0 | — |
| `di` | 0 | 11 | 6 | 0 | — |
| `formatter` | 0 | 10 | 5 | 0 | — |
| `health` | 0 | 2 | 3 | 1 | `di` |
| `lint` | 0 | 26 | 0 | 0 | — |
| `log` | 0 | 8 | 4 | 1 | `context` |
| `select` | 0 | 2 | 2 | 0 | — |
| `kernel` | 1 | 10 | 6 | 1 | `log` |
| `authoring` | 2 | 6 | 6 | 3 | `di`, `formatter`, `kernel` |
| `runtime` | 3 | 4 | 6 | 7 | `authoring`, `context`, `di`, `health`, `kernel`, `log`, `select` |
| `connections` | 4 | 10 | 0 | 3 | `authoring`, `di`, `runtime` |
| `dispatch` | 4 | 9 | 3 | 6 | `authoring`, `context`, `di`, `kernel`, `log`, `runtime` |
| `auth` | 5 | 10 | 0 | 1 | `context` |
| `cli` | 5 | 6 | 0 | 9 | `authoring`, `context`, `dispatch`, `formatter`, `health`, `kernel`, `mcp`, `runtime`, `select` |
| `codemode` | 5 | 5 | 1 | 1 | `formatter` |
| `http` | 5 | 5 | 0 | 6 | `context`, `di`, `dispatch`, `health`, `kernel`, `runtime` |
| `mcp` | 5 | 8 | 2 | 7 | `authoring`, `codemode`, `context`, `dispatch`, `formatter`, `kernel`, `runtime` |
| `otel` | 5 | 3 | 0 | 0 | — |
| `testing` | 6 | 7 | 0 | 6 | `authoring`, `context`, `formatter`, `log`, `mcp`, `runtime` |

## Layer-ordered DAG

### Layer 0

- `context` → no cross-unit dependencies
- `di` → no cross-unit dependencies
- `formatter` → no cross-unit dependencies
- `health` → `di`
- `lint` → no cross-unit dependencies
- `log` → `context`
- `select` → no cross-unit dependencies

### Layer 1

- `kernel` → `log`

### Layer 2

- `authoring` → `di`, `formatter`, `kernel`

### Layer 3

- `runtime` → `authoring`, `context`, `di`, `health`, `kernel`, `log`, `select`

### Layer 4

- `connections` → `authoring`, `di`, `runtime`
- `dispatch` → `authoring`, `context`, `di`, `kernel`, `log`, `runtime`

### Layer 5

- `auth` → `context`
- `cli` → `authoring`, `context`, `dispatch`, `formatter`, `health`, `kernel`, `mcp`, `runtime`, `select`
- `codemode` → `formatter`
- `http` → `context`, `di`, `dispatch`, `health`, `kernel`, `runtime`
- `mcp` → `authoring`, `codemode`, `context`, `dispatch`, `formatter`, `kernel`, `runtime`
- `otel` → no cross-unit dependencies

### Layer 6

- `testing` → `authoring`, `context`, `formatter`, `log`, `mcp`, `runtime`
