# a2kit lint rules (v0.4.1)

Three layers — all three are mandatory in this repo's CI:

- **Type-checked layer — mandatory.** Caught by `ty` (or any PEP 695-aware
  checker) before runtime. Zero AST cost. `ty>=0.0.34` is a dev-dependency;
  CI hard-fails on any diagnostic from `uv run ty check src/`. The previous
  "graceful skip" mode was removed in v0.4.1.
- **AST-checked** — `uvx a2kit lint paths...` walks source. No imports executed.
- **Runtime-checked** — `uvx a2kit check --import path:server` — needs an
  importable FastMCP server.

Configurable via `[tool.a2kit.lint]` and `[tool.a2kit.check]` in `pyproject.toml`.
Per-line ignores via `# noqa: A2KXXX`.

## Type-checked (mandatory)

These are the rules ty (or pyright) catches at compile time. AST fallback is
listed below for cross-checker portability, but in this repo ty is a hard
gate, not a graceful skip.

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

### A2K005 — Legacy `KEY_FIELDS` migration aid + tool-param compat against `cls.Key`

v0.5: `KEY_FIELDS` is removed. The lint rule now (a) flags any leftover
`KEY_FIELDS = ...` declaration on a `ConnectionInfo` subclass as a migration
error, and (b) continues to cross-check tool `connection_param` arity against
`cls.Key._fields` of the resolved store.

For (b), when a `@a2kit.tool(store=widget_store, connection_param="conn")`
decoration references a store whose `ConnectionInfo` declares
`class WidgetConn(ConnectionInfo, key=WidgetKey)` and `WidgetKey` has arity > 1,
the function's `conn` parameter type annotation must be one of:

- The NamedTuple key class itself (e.g. `WidgetKey`)
- `tuple[str, ...]` / `tuple[str, str, ...]` (matching arity)
- `dict[str, str]`

Bare `str` is rejected for arity > 1 (only valid for arity == 1, i.e. the
default `_DefaultKey(name)` shape). The lint walks the AST to resolve the
store's `ConnectionInfo` class — and from there its `key=` NamedTuple — within
the same file. If the store is imported from another module, the rule degrades
to an advisory (`could not resolve store ...; check arity manually`).

### A2K010 — Unknown atom in a `--select` expression

Activated in v0.4. The lint scans `--select` strings in source files (any
`MCPRunner(default_select=...)`, `parse_select(...)`, or `--select "<expr>"`
inside argv lists / `subprocess.run(...)` calls), shell scripts (`scripts/*.sh`),
Makefiles, and the `[tool.a2kit.runner] default_select` value in
`pyproject.toml`. Each atom is parsed and validated against the union of
declared routers, tool names, capability names, and the special `default` atom.
Unknown atoms raise A2K010 with `difflib.get_close_matches` suggestions.

### A2K011 — Tools should return Pydantic models (advisory, warning)

When a `@a2kit.tool` function declares a `-> dict` / `-> Mapping` return,
the schema-snapshot harness can't extract a typed shape and falls back to a
permissive schema. Returning a Pydantic `BaseModel` lets
`model.model_json_schema()` produce a tight, version-controllable schema. This
rule is advisory (not error). Configurable via
`[tool.a2kit.lint] disabled = ["A2K011"]`. Suppressible via
`# noqa: A2K011` on the function definition line.

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
