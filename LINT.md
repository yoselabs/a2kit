# a2kit lint rules (v0.3.1)

Three layers — pick the strictest your CI tolerates:

- **Type-checked** — caught by `ty --strict` (or any PEP 695-aware checker)
  before runtime. Zero AST cost.
- **AST-checked** — `uvx a2kit lint paths...` walks source. No imports executed.
- **Runtime-checked** — `uvx a2kit check --import path:server` — needs an
  importable FastMCP server.

Configurable via `[tool.a2kit.lint]` and `[tool.a2kit.check]` in `pyproject.toml`.
Per-line ignores via `# noqa: A2KXXX`.

## Type-checked

These are the rules ty (or pyright) catches at compile time. AST fallback is
listed below for users without a strict type checker.

| Type-system signal | Caught at | AST fallback |
|---|---|---|
| `-> str` return from a tool | `R` `TypeVar` bound on `@a2kit.tool` overloads | A2K002 |
| Missing `connection_param` declaration | n/a — best caught by tests / lint | A2K001 |
| Bare `Any` / missing annotation in src/ | ruff `ANN` rules | — |
| Unknown kwarg on `@a2kit.tool` | `ToolConfig(extra="forbid")` at decoration | — |
| Unknown kwarg on `MCPRunner` | `RunnerConfig(extra="forbid")` | — |
| Raw `'write'` cap string | (no ty signal — strings are subtype of `str`) | A2K009 |

## AST-checked (`a2kit lint`)

### A2K001 — Tool decorator missing param

A function decorated with `@a2kit.tool(connection_param="X")` must declare a parameter named `X`.

### A2K002 — No `-> str` returns from tools

FastMCP double-serialises string returns. Tools must return dicts or Pydantic models.

### A2K003 — Module-local Pydantic return types

Locally-defined Pydantic classes used as tool return annotations are flagged.

### A2K004 — Connection-param canonical helper

A tool with a parameter named `connection` must reference `a2kit.docs.connection_param_doc()`.

### A2K005 — `KEY_FIELDS` shape and usage

A `ConnectionInfo` subclass declaring `KEY_FIELDS` must use a tuple of lowercase
Python identifier strings. v0.3.1 also runs the same checks at class-creation
time via `ConnectionInfo.__init_subclass__`.

### A2K006 — Duplicate param description across tools

If the same parameter has the same docstring text in three or more tools across
a project, A2K006 suggests `a2kit.docs.register_param_doc(name, text)`.

### A2K008 — Name collision

A router name, registered capability, or tool name overlaps within the same
project. Hard error. Skipped on `tests/` and `examples/` paths.

### A2K009 — Raw built-in capability string

`capabilities={'write'}` literal where `Cap.WRITE` would be type-safer. Warning.
Skipped on `tests/` and `examples/` paths.

### A2K010 — (reserved for v0.4)

Unknown atom in `--select` expression in source files / pyproject. Stub'd; not
yet active.

## Runtime-checked (`a2kit check`)

### A2KR001 — Snapshot file presence

For each tool registered on the imported FastMCP server, a snapshot file must
exist at the configured snapshot directory. Run with `--update-schema-snapshots`
to regenerate.

### A2KR002 — Per-tool budget compliance

Each snapshot file must be ≤ its declared byte budget.

### A2KR003 — Total schema budget

Sum of snapshot file sizes ≤ total byte budget.

### A2KR004 — Similar tool names

Tool names with edit-distance < 2 confuse agents. Standalone hook also lives at
`scripts/find_similar.py`.

## Configuration

```toml
[tool.a2kit.lint]
disabled = ["A2K004"]    # don't enforce the canonical helper rule

[tool.a2kit.check]
disabled = ["A2KR004"]   # don't enforce similar-tool-names

[tool.a2kit.runner]
default_select = "default and not write and not destructive"

[tool.a2kit.budgets]
total = 0                # disable total-schema budget
```

CLI override: `a2kit lint --disabled A2K004 src/`.

## Pre-commit

See `.pre-commit-config.yaml` at repo root — wires `a2kit lint`, ruff,
ruff-format, and actionlint.
