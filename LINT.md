# a2kit lint rules (v0.3)

Two layers, both invoked from `uvx a2kit`:

- **`a2kit lint paths...`** — static AST rules (`A2K001`..`A2K006`). No imports executed.
- **`a2kit check --import path:server`** — runtime checks (`A2KR001`..`A2KR004`).

Configurable via `[tool.a2kit.lint]` and `[tool.a2kit.check]` in `pyproject.toml`. Per-line ignores via `# noqa: A2KXXX`.

## Static rules

### A2K001 — Tool decorator missing param

A function decorated with `@a2kit.tool(connection_param="X")` must declare a parameter named `X`.

```python
# fails A2K001
@a2kit.tool(connection_param="conn")
def f(x: str) -> dict: ...

# passes
@a2kit.tool(connection_param="conn")
def f(conn: str) -> dict: ...
```

Disable: `# noqa: A2K001` on the function definition line.

### A2K002 — No `-> str` returns from tools

FastMCP double-serialises string returns (the a2db `4d07632` bug). Tools must return dicts or Pydantic models. The runtime decorator already enforces this; A2K002 surfaces the failure at lint time.

### A2K003 — Module-local Pydantic return types

Locally-defined Pydantic classes (subclasses of `BaseModel` or `ConnectionInfo` in the same file) used as tool return annotations are flagged. Reuse models from a central schema module instead.

Skipped on files under `tests/` and `examples/` paths.

### A2K004 — Connection-param canonical helper

A tool with a parameter literally named `connection` must reference `a2kit.docs.connection_param_doc()` somewhere in the module (so the docstring text stays canonical). 

Skipped on files under `tests/` and `examples/` paths.

### A2K005 — `KEY_FIELDS` shape and usage

A `ConnectionInfo` subclass that declares `KEY_FIELDS` must use a tuple of lowercase Python identifier strings.

Examples:

```python
# passes
class C(a2kit.ConnectionInfo):
    KEY_FIELDS = ("project", "env", "db")

# A2K005: "must be a tuple"
class C(a2kit.ConnectionInfo):
    KEY_FIELDS = "name"

# A2K005: "should be lowercase"
class C(a2kit.ConnectionInfo):
    KEY_FIELDS = ("Project", "env", "db")

# A2K005: "is not a valid identifier"
class C(a2kit.ConnectionInfo):
    KEY_FIELDS = ("a-b",)
```

### A2K006 — Duplicate param description across tools

If the same parameter name has the same docstring text (≥ 20 chars) in three or more tools across a project, A2K006 suggests moving the text to `a2kit.docs.register_param_doc(name, text)`.

## Runtime checks

### A2KR001 — Snapshot file presence

For each tool registered on the imported FastMCP server, a snapshot file must exist at the configured snapshot directory. Run with `--update-schema-snapshots` to regenerate.

Configure: `--snapshot-dir <path>` on the CLI.

### A2KR002 — Per-tool budget compliance

Each snapshot file must be ≤ its declared byte budget. Budgets come from the runner config (e.g. a `budgets` dict passed to `run_runtime_checks`).

### A2KR003 — Total schema budget

Sum of snapshot file sizes ≤ total byte budget. Configure via `--total-budget <bytes>`.

### A2KR004 — Similar tool names

Tool names with edit-distance < 2 confuse agents (e.g. `get_issue` vs `get_issues`). Rename one or merge them.

## Configuration

```toml
[tool.a2kit.lint]
disabled = ["A2K004"]    # don't enforce the canonical helper rule

[tool.a2kit.check]
disabled = ["A2KR004"]   # don't enforce similar-tool-names
```

CLI override: `a2kit lint --disabled A2K004 src/`.

## Pre-commit

Wire `a2kit lint` and `a2kit check` into `.pre-commit-config.yaml`:

```yaml
- id: a2kit-lint
  name: a2kit static lint
  entry: uv run a2kit lint src/ tests/ examples/
  language: system
  pass_filenames: false
  always_run: true
```
